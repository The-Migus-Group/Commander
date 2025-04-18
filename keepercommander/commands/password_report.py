#  _  __
# | |/ /___ ___ _ __  ___ _ _ ®
# | ' </ -_) -_) '_ \/ -_) '_|
# |_|\_\___\___| .__/\___|_|
#              |_|
#
# Keeper Commander
# Copyright 2023 Keeper Security Inc.
# Contact: ops@keepersecurity.com
#

import argparse
import logging

from .base import report_output_parser, Command, try_resolve_path, FolderMixin, dump_report_data, field_to_title
from ..error import CommandError
from .. import vault, generator, vault_extensions, utils

password_report_parser = argparse.ArgumentParser(prog='password-report', parents=[report_output_parser], description='Display record password report.')
password_report_parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', help='Display verbose information')
password_report_parser.add_argument('--policy', dest='policy', action='store',
                                    help='Password complexity policy. Length,Lower,Upper,Digits,Special. Default is 12,2,2,2,0')
password_report_parser.add_argument('-l', '--length', dest='length', type=int, action='store', help='Minimum password length.')
password_report_parser.add_argument('-u', '--upper', dest='upper', type=int, action='store', help='Minimum uppercase characters.')
password_report_parser.add_argument('--lower', dest='lower', type=int, action='store', help='Minimum lowercase characters.')
password_report_parser.add_argument('-d', '--digits', dest='digits', type=int, action='store', help='Minimum digits.')
password_report_parser.add_argument('-s', '--special', dest='special', type=int, action='store', help='Minimum special characters.')
password_report_parser.add_argument('folder', nargs='?', type=str, action='store', help='folder path or UID')


class PasswordReportCommand(Command):
    def get_parser(self):
        return password_report_parser

    def execute(self, params, **kwargs):
        verbose = kwargs.get('verbose') is True
        p_length = 0
        p_lower = 0
        p_upper = 0
        p_digits = 0
        p_special = 0

        policy = kwargs.get('policy')
        if policy:
            comps = [x.strip() for x in policy.split(',')]
            if any(False for c in comps if len(c) > 0 and not c.isdigit()):
                raise CommandError('Invalid policy format.  Must be list of integer values separated by commas.')
            if len(comps) > 0:
                if comps[0]:
                    p_length = int(comps[0])
            if len(comps) > 1:
                if comps[1]:
                    p_lower = int(comps[1])
            if len(comps) > 2:
                if comps[2]:
                    p_upper = int(comps[2])
            if len(comps) > 3:
                if comps[3]:
                    p_digits = int(comps[3])
            if len(comps) > 4:
                if comps[4]:
                    p_special = int(comps[4])
        else:
            if isinstance(kwargs.get('length'), int):
                p_length = kwargs.get('length')
            if isinstance(kwargs.get('upper'), int):
                p_upper = kwargs.get('upper')
            if isinstance(kwargs.get('lower'), int):
                p_lower = kwargs.get('lower')
            if isinstance(kwargs.get('digits'), int):
                p_digits = kwargs.get('digits')
            if isinstance(kwargs.get('special'), int):
                p_special = kwargs.get('special')

        if p_length <= 0 and p_upper <= 0 and p_lower <= 0 and p_digits <= 0 and p_special <= 0:
            raise CommandError('', 'Password policy must be specified.')

        path_or_uid = kwargs.get('folder')
        folder_uid = ''
        if path_or_uid:
            if path_or_uid in params.folder_cache:
                folder_uid = path_or_uid
            else:
                rs = try_resolve_path(params, path_or_uid)
                if rs is None:
                    raise CommandError('', f'Folder path {path_or_uid} not found')
                folder, pattern = rs
                if not folder or pattern:
                    raise CommandError('', f'Folder path {path_or_uid} not found')
                folder_uid = folder.uid or ''

        records = list(FolderMixin.get_records_in_folder_tree(params, folder_uid))
        table = []
        header = ['record_uid', 'title', 'description', 'length', 'lower', 'upper', 'digits', 'special']
        password_count = {}
        if verbose:
            header.append('score')
            if params.breach_watch:
                header.extend(['status', 'reused'])
                for record_uid, bw_record in params.breach_watch_records.items():
                    if record_uid in params.record_cache:
                        if isinstance(bw_record, dict):
                            data = bw_record.get('data_unencrypted')
                            if isinstance(data, dict):
                                passwords = data.get('passwords')
                                if isinstance(passwords, list):
                                    for pwd in passwords:
                                        password = pwd.get('value')
                                        if password:
                                            if password in password_count:
                                                password_count[password] += 1
                                            else:
                                                password_count[password] = 1

        fmt = kwargs.get('format')
        for record_uid in records:
            record = vault.KeeperRecord.load(params, record_uid)
            if not record:
                continue
            if record.version not in (2, 3):
                continue
            password = ''
            if isinstance(record, vault.PasswordRecord):
                password = record.password
            elif isinstance(record, vault.TypedRecord):
                password_field = record.get_typed_field('password')
                if password_field:
                    password = password_field.get_default_value(str)
            else:
                continue
            if not password:
                continue
            strength = generator.get_password_strength(password)
            password_ok = (strength.length >= p_length and strength.caps >= p_upper and strength.lower >= p_lower and
                           strength.digits >= p_digits and strength.symbols >= p_special)
            if password_ok:
                continue

            title = record.title
            if len(title) > 32:
                title = title[:30] + '...'
            description = vault_extensions.get_record_description(record)
            if isinstance(description, str):
                if len(description) > 32:
                    description = description[:30] + '...'
            row = [record_uid, title, description, strength.length, strength.lower, strength.caps, strength.digits, strength.symbols]
            if verbose:
                row.append(utils.password_score(password))
                if params.breach_watch:
                    status = ''
                    reused = None
                    bw_record = params.breach_watch_records.get(record_uid)
                    if isinstance(bw_record, dict):
                        data = bw_record.get('data_unencrypted')
                        if isinstance(data, dict):
                            passwords = data.get('passwords')
                            if isinstance(passwords, list):
                                password_status = next((x for x in passwords if x.get('value') == password), None)
                                if isinstance(password_status, dict):
                                    status = password_status.get('status')
                    if password in password_count:
                        reused_count = password_count[password]
                        if isinstance(reused_count, int) and reused_count > 1:
                            reused = reused_count
                    row.extend([status, reused])

            table.append(row)

        if fmt != 'json':
            header = [field_to_title(x) for x in header]

        logging.info('')
        if p_length > 0:
            logging.info('     Password Length: %d', p_length)
        if p_lower > 0:
            logging.info('Lowercase characters: %d', p_lower)
        if p_upper > 0:
            logging.info('Uppercase characters: %d', p_upper)
        if p_digits > 0:
            logging.info('              Digits: %d', p_digits)
        if p_special > 0:
            logging.info('  Special characters: %d', p_special)
        logging.info('')

        return dump_report_data(table, header, fmt=fmt, filename=kwargs.get('output'), row_number=True)
