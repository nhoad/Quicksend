#!/usr/bin/env python
'''
File: main.py
Author: Nathan Hoad
Description: quicksend is a small application to monitor a directory and send files based on file extension rules.
'''
import sys
import shutil
import os
import configparser
import logging
import smtplib
import datetime

from pyinotify import WatchManager, ProcessEvent, IN_CLOSE_WRITE, IN_CLOSE_NOWRITE, Notifier
from smtplib import SMTPAuthenticationError
from email import encoders
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate

config_path = os.path.join(os.environ['HOME'], '.quicksend/config')

default_options = {}

default_options['watch_directory'] = os.path.join(os.environ['HOME'], '.quicksend/unsent')
default_options['sent_directory'] = os.path.join(os.environ['HOME'], '.quicksend/sent')
default_options['email_body'] = ''
default_options['email_subject'] = 'Timelog for week ending %%d %%B'
default_options['sender_email'] = 'nathan@getoffmalawn.com'
default_options['smtp_server'] = 'smtp.gmail.com'
default_options['smtp_port'] = '587'
default_options['smtp_use_tls'] = 'yes'
default_options['log_file'] = os.path.join(os.environ['HOME'], '.quicksend/quicksend.log')

class FolderWatch(ProcessEvent):
    def __init__(self, config):
        self.config = config
        get = config.get
        getboolean = config.getboolean

        self.account = (get('settings', 'sender_email'), get('settings', 'password'))
        self.smtp_info = (get('settings', 'smtp_server'), get('settings', 'smtp_port'), getboolean('settings', 'smtp_use_tls'))
        self.log_file = get('settings', 'log_file')
        self.email = (get('settings', 'email_body'), get('settings', 'email_subject'))

        filetypes = config.items('filetypes')

        f = {}

        for key, contact in filetypes:
            f[key] = contact

        self.files = f

    def process_IN_CLOSE(self, event):
        n = os.path.join(event.path, event.name)
        new_location = self.config.get('settings', 'sent_directory')

        for i in self.files.keys():
            if n.endswith(i):
                f = self.files[i]
                self.send_email(f, n, new_location)
                break

    def send_email(self, address, file_name, moved):
        logging.info('Sending {} to {}'.format(file_name, address))

        server, port, tls = self.smtp_info
        username, password = self.account
        type = os.path.split(file_name)[1]
        body = self.config.get(type, 'message')
        subject = self.config.get(type, 'subject')

        port = int(port)

        sender = smtplib.SMTP(server, port)
        sender.ehlo()
        if tls:
            sender.starttls()
        sender.ehlo()
        sender.login(username, password)

        msg = MIMEMultipart()
        msg['From'] = username
        msg['To'] = ', '.join([address])
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = datetime.datetime.now().strftime(subject)
        msg.attach(MIMEText(body))

        data = None

        with open(file_name, 'rb') as f:
            data = f.read()

        part = MIMEBase('application', 'octet-stream')
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment; filename="{}"'.format(os.path.basename(file_name)))
        msg.attach(part)

        sender.sendmail(username, address, msg.as_string())
        shutil.move(file_name, moved)
        logging.info('message sent!')


class Monitor():
    def __init__(self, config):
        get = config.get

        directory = get('settings', 'watch_directory')
        wm = WatchManager()
        notifier = Notifier(wm, FolderWatch(config))
        wm.add_watch(directory, IN_CLOSE_WRITE, rec=True)

        logging.basicConfig(filename=get('settings', 'log_file'), level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M%S')

        while True:
            try:
                notifier.process_events()
                if notifier.check_events():
                    notifier.read_events()
            except KeyboardInterrupt:
                notifier.stop()
                break

if __name__ == '__main__':
    conf = configparser.ConfigParser(default_options)

    if not conf.read(config_path):
        print('No .quicksend config could be found in your home directory. Consult the documentation.', file=sys.stderr)
        sys.exit(1)

    try:
        Monitor(conf)
    except configparser.NoOptionError as e:
        print('{}. Consult the documentation for help or add the missing option to your config file'.format(e))
        sys.exit(2)
    except SMTPAuthenticationError as e:
        message = 'Error logging into SMTP: {}'.format(e)
        print(e, file=sys.stderr)
        logging.critical(message)
        sys.exit(4)
    except shutil.Error as e:
        message = 'Error logging into SMTP: {}'.format(e)
        print(e, file=sys.stderr)
        logging.critical(message)
        sys.exit(5)
