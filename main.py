import os
import pandas as pd
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext, CallbackQueryHandler
from gtts import gTTS
from pygooglevoice import Voice
from pygooglevoice.exceptions import AuthenticationError
import time

# Telegram Bot Token
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'

# Google Text-to-Speech Credentials
GOOGLE_TTS_CREDENTIALS = 'path/to/your/google-credentials.json'

# Initialize Telegram Bot
updater = Updater(TELEGRAM_TOKEN, use_context=True)
dispatcher = updater.dispatcher

# Load client data
clients = pd.read_csv('clients.csv')

# Conversation states
ADD_GV, IMPORT_SCRIPT, START_BATCH, EDIT_SCRIPT, EDIT_GV = range(5)

# DND check toggle
dnd_check_enabled = False

def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("Add Google Voice", callback_data='addgv')],
        [InlineKeyboardButton("Import Script", callback_data='importscript')],
        [InlineKeyboardButton("Edit Script", callback_data='editscript')],
        [InlineKeyboardButton("Edit Google Voice", callback_data='editgv')],
        [InlineKeyboardButton("Start Batch Call", callback_data='startbatch')],
        [InlineKeyboardButton("Toggle DND Check", callback_data='dndcheck')],
        [InlineKeyboardButton("View Script", callback_data='viewscript')],
        [InlineKeyboardButton("View Google Voice Accounts", callback_data='viewgv')]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text('Welcome! Please choose an option:', reply_markup=reply_markup)

def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    if query.data == 'addgv':
        query.edit_message_text(text="Please provide your Google Voice credentials in the format:\n"
                                     "google voice email:password:backup email:backup email code (if asked)")
        return ADD_GV
    elif query.data == 'importscript':
        query.edit_message_text(text="Please provide your custom script. Use {name}, {email}, and {platform} as placeholders.")
        return IMPORT_SCRIPT
    elif query.data == 'editscript':
        query.edit_message_text(text="Please provide the new script. Use {name}, {email}, and {platform} as placeholders.")
        return EDIT_SCRIPT
    elif query.data == 'editgv':
        query.edit_message_text(text="Please provide the Google Voice account details you want to edit in the format:\n"
                                     "old email:new email:new password:new backup email:new backup email code (if asked)")
        return EDIT_GV
    elif query.data == 'startbatch':
        query.edit_message_text(text="Drop your data file here.")
        return START_BATCH
    elif query.data == 'dndcheck':
        global dnd_check_enabled
        dnd_check_enabled = not dnd_check_enabled
        query.edit_message_text(text=f'DND check is now {"enabled" if dnd_check_enabled else "disabled"}.')
    elif query.data == 'viewscript':
        script = context.user_data.get('script', default_script)
        query.edit_message_text(text=f'Current script:\n{script}')
    elif query.data == 'viewgv':
        gv_accounts = context.user_data.get('gv_accounts', [])
        query.edit_message_text(text='Current Google Voice accounts:\n' + '\n'.join(gv_accounts))

def handle_add_gv(update: Update, context: CallbackContext) -> int:
    credentials = update.message.text.split(':')
    if len(credentials) < 3 or len(credentials) > 4:
        update.message.reply_text('Invalid format. Please try again.')
        return ADD_GV

    email, password, backup_email = credentials[:3]
    backup_code = credentials[3] if len(credentials) == 4 else None

    voice = Voice()
    try:
        voice.login(email, password, backup_email, backup_code)
        update.message.reply_text('Google Voice account added successfully.')
        context.user_data.setdefault('gv_accounts', []).append(email)
    except AuthenticationError as e:
        update.message.reply_text(f'Error: {e}')

    return ConversationHandler.END

def handle_import_script(update: Update, context: CallbackContext) -> int:
    script = update.message.text
    context.user_data['script'] = script
    update.message.reply_text('Script imported successfully.')
    return ConversationHandler.END

def handle_edit_script(update: Update, context: CallbackContext) -> int:
    script = update.message.text
    context.user_data['script'] = script
    update.message.reply_text('Script edited successfully.')
    return ConversationHandler.END

def handle_edit_gv(update: Update, context: CallbackContext) -> int:
    details = update.message.text.split(':')
    if len(details) < 4 or len(details) > 5:
        update.message.reply_text('Invalid format. Please try again.')
        return EDIT_GV

    old_email, new_email, new_password, new_backup_email = details[:4]
    new_backup_code = details[4] if len(details) == 5 else None

    voice = Voice()
    try:
        voice.login(old_email, new_password, new_backup_email, new_backup_code)
        update.message.reply_text('Google Voice account edited successfully.')
        context.user_data['gv_accounts'] = [new_email if email == old_email else email for email in context.user_data.get('gv_accounts', [])]
    except AuthenticationError as e:
        update.message.reply_text(f'Error: {e}')

    return ConversationHandler.END

def handle_start_batch(update: Update, context: CallbackContext) -> int:
    if 'document' in update.message:
        file = update.message.document.get_file()
        file.download('clients.txt')
        update.message.reply_text('Data file received. Starting batch calls.')
        with open('clients.txt', 'r') as f:
            lines = f.readlines()
            for line in lines:
                name, platform, email, phone = line.strip().split()
                script = context.user_data.get('script', default_script)
                script = script.format(name=name, email=email, platform=platform)

                # Convert script to speech
                tts = gTTS(text=script, lang='en')
                tts.save("output.mp3")

                # Make the call
                try:
                    call = voice.call(phone)
                    call.play("output.mp3")
                    update.message.reply_text(f'Calling {phone} with the script.')
                except AuthenticationError as e:
                    update.message.reply_text(f'Error: {e}')
    else:
        update.message.reply_text('No data file received. Please try again.')
    return ConversationHandler.END

def call(update: Update, context: CallbackContext) -> None:
    args = context.args
    if len(args) != 4:
        update.message.reply_text('Usage: /call <name> <platform> <email> <phone>')
        return

    name, platform, email, phone = args
    script = context.user_data.get('script', default_script)
    script = script.format(name=name, email=email, platform=platform)

    # Convert script to speech
    tts = gTTS(text=script, lang='en')
    tts.save("output.mp3")

    # Make the call
    try:
        call = voice.call(phone)
        call.play("output.mp3")
        update.message.reply_text(f'Calling {phone} with the script.')
    except AuthenticationError as e:
        update.message.reply_text(f'Error: {e}')

# Conversation handlers
conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(button, pattern='^addgv$|^importscript$|^editscript$|^editgv$|^startbatch$')],
    states={
        ADD_GV: [MessageHandler(Filters.text & ~Filters.command, handle_add_gv)],
        IMPORT_SCRIPT: [MessageHandler(Filters.text & ~Filters.command, handle_import_script)],
        EDIT_SCRIPT: [MessageHandler(Filters.text & ~Filters.command, handle_edit_script)],
        EDIT_GV: [MessageHandler(Filters.text & ~Filters.command, handle_edit_gv)],
        START_BATCH: [MessageHandler(Filters.document.mime_type("text/plain"), handle_start_batch)]
    },
    fallbacks=[CommandHandler('cancel', ConversationHandler.END)]
)

dispatcher.add_handler(conv_handler)
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("call", call))
dispatcher.add_handler(CallbackQueryHandler(button))

updater.start_polling()
updater.idle()
