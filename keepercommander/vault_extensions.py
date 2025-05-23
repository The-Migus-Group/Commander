#  _  __
# | |/ /___ ___ _ __  ___ _ _ ®
# | ' </ -_) -_) '_ \/ -_) '_|
# |_|\_\___\___| .__/\___|_|
#              |_|
#
# Keeper Commander
# Contact: ops@keepersecurity.com
#

import abc
import itertools
import re
from typing import Optional, Union, Iterator, Dict, Set, Callable, Any, Iterable

from . import crypto, utils, vault, record_types
from .params import KeeperParams


def _match_value(pattern, value):  # type: (Callable[[str], Any], Any) -> bool
    if isinstance(value, str):
        if pattern(value):
            return True
    elif isinstance(value, list):
        for v in value:
            if _match_value(pattern, v):
                return True
    elif isinstance(value, dict):
        for v in value.values():
            if _match_value(pattern, v):
                return True
    return False


def matches_record(record, pattern, search_fields=None):    # type: (vault.KeeperRecord, Union[str, Callable[[str], Any]], Optional[Iterable[str]]) -> bool
    if isinstance(pattern, str):
        pattern = re.compile(pattern, re.IGNORECASE).search

    if search_fields is not None:
        search_fields = {f.lower() for f in search_fields}

    for key, value in record.enumerate_fields():
        m = re.match(r'^\((\w+)\)\.?', key)
        if m:
            key = m.group(1)
        if search_fields is not None and key.lower() not in search_fields:
            continue
        if key and _match_value(pattern, key):
            return True
        if value and _match_value(pattern, value):
            return True
    return False


def find_records(params,                   # type: KeeperParams
                 search_str=None,          # type: Optional[str]
                 record_type=None,         # type: Union[str, Iterable[str], None]
                 record_version=None,      # type: Union[int, Iterable[int], None]
                 search_fields=None        # type: Optional[Iterable[str]]
                 ):                       # type: (...) -> Iterator[vault.KeeperRecord]
    pattern = re.compile(search_str, re.IGNORECASE).search if search_str else None

    type_filter = None       # type: Optional[Set[str]]
    version_filter = None    # type: Optional[Set[int]]
    if record_type:
        type_filter = set()
        if isinstance(record_type, str):
            type_filter.add(record_type)
        if isinstance(record_type, Iterable):
            type_filter.update(record_type)

    if record_version:
        version_filter = set()
        if isinstance(record_version, int):
            version_filter.add(record_version)
        if isinstance(record_version, Iterable):
            version_filter.update((x for x in record_version if isinstance(x, int)))

    for record_uid in params.record_cache:
        record = vault.KeeperRecord.load(params, record_uid)
        if not record:
            continue
        if search_str and record.record_uid == search_str:
            yield record
            continue
        if version_filter and record.version not in version_filter:
            continue
        if type_filter and record.record_type not in type_filter:
            continue

        if pattern:
            is_match = matches_record(record, pattern, search_fields)
        else:
            is_match = True
        if is_match:
            yield record


def get_record_description(record):   # type: (vault.KeeperRecord) -> Optional[str]
    comps = []

    if isinstance(record, vault.PasswordRecord):
        comps.extend((record.login or '', record.link or ''))
        return ' @ '.join((str(x) for x in comps if x))

    if isinstance(record, vault.TypedRecord):
        if record.version == 6:
            return 'PAM Configuration'
        field = next((x for x in record.fields if x.type == 'login'), None)
        if field:
            value = field.get_default_value()
            if value:
                comps.append(field.get_default_value() or '')
                field = next((x for x in record.fields if x.type == 'url'), None)
                if field:
                    comps.append(field.get_default_value())
                else:
                    field = next((x for x in itertools.chain(record.fields, record.custom) if x.type.lower() in {'host', 'pamhostname'}), None)
                    if field:
                        host = field.get_default_value()
                        if isinstance(host, dict):
                            address = host.get('hostName')
                            if address:
                                port = host.get('port')
                                if port:
                                    address = f'{address}:{port}'
                                comps.append(address)
                return ' @ '.join((str(x) for x in comps if x))

        field = next((x for x in record.fields if x.type == 'paymentCard'), None)
        if field:
            value = field.get_default_value()
            if isinstance(value, dict):
                number = value.get('cardNumber') or ''
                if isinstance(number, str):
                    if len(number) > 4:
                        number = '*' + number[-4:]
                        comps.append(number)

                field = next((x for x in record.fields if x.type == 'text' and x.label == 'cardholderName'), None)
                if field:
                    name = field.get_default_value()
                    if name and isinstance(name, str):
                        comps.append(name.upper())
                return ' / '.join((str(x) for x in comps if x))

        field = next((x for x in record.fields if x.type == 'bankAccount'), None)
        if field:
            value = field.get_default_value()
            if isinstance(value, dict):
                routing = value.get('routingNumber') or ''
                if routing:
                    routing = '*' + routing[-3:]
                account = value.get('accountNumber') or ''
                if account:
                    account = '*' + account[-3:]
                if routing or account:
                    if routing and account:
                        return f'{routing} / {account}'
                    else:
                        return routing if routing else account

        field = next((x for x in record.fields if x.type == 'keyPair'), None)
        if field:
            value = field.get_default_value()
            if isinstance(value, dict):
                if value.get('privateKey'):
                    comps.append('<Private Key>')
                if value.get('publicKey'):
                    comps.append('<Public Key>')
            return ' / '.join((str(x) for x in comps if x))

        field = next((x for x in record.fields if x.type == 'address'), None)
        if field:
            value = field.get_default_value()
            if isinstance(value, dict):
                comps.extend((
                    f'{value.get("street1", "")} {value.get("street2", "")}'.strip(),
                    f'{value.get("city", "")}',
                    f'{value.get("state", "")} {value.get("zip", "")}'.strip(),
                    f'{value.get("country", "")}'))
            return ', '.join((str(x) for x in comps if x))

        field = next((x for x in record.fields if x.type == 'name'), None)
        if field:
            value = field.get_default_value()
            if isinstance(value, dict):
                comps.extend((value.get('first', ''), value.get('middle', ''), value.get('last', '')))
                return ' '.join((str(x) for x in comps if x))

    if isinstance(record, vault.FileRecord):
        comps.extend((record.name, utils.size_to_str(record.size)))
        return ', '.join((str(x) for x in comps if x))


def extract_password_record_data(record):  # type: (vault.PasswordRecord) -> dict
    if isinstance(record, vault.PasswordRecord):
        return {
            'title': record.title or '',
            'secret1': record.login or '',
            'secret2': record.password or '',
            'link': record.link or '',
            'notes': record.notes or '',
            'custom': [{
                'name': x.name or '',
                'value': x.value or '',
                'type': x.type or 'text',
            } for x in record.custom]
        }
    else:
        raise ValueError('extract_password_record_data: V2 record is expected')


def extract_password_record_extras(record, existing_extra=None):
    # type: (vault.PasswordRecord, Optional[dict]) -> dict
    if isinstance(record, vault.PasswordRecord):
        extra = existing_extra if isinstance(existing_extra, dict) else {}

        if 'fields' not in extra:
            extra['fields'] = []

        extra['files'] = []
        if record.attachments:
            for atta in record.attachments:
                extra_file = {
                    'id': atta.id,
                    'key': atta.key,
                    'name': atta.name,
                    'size': atta.size,
                    'type': atta.mime_type,
                    'title': atta.title,
                    'lastModified': atta.last_modified,
                    'thumbs': [{'id': x.id, 'type': x.type, 'size': x.size} for x in atta.thumbnails or []]
                }
                extra['files'].append(extra_file)
        totp_field = next((x for x in extra['fields'] if x.get('field_type') == 'totp'), None)
        if record.totp:
            if not totp_field:
                totp_field = {
                    'id': utils.base64_url_encode(crypto.get_random_bytes(8)),
                    'field_type': 'totp',
                    'field_title': ''
                }
                extra['fields'].append(totp_field)
            totp_field['data'] = record.totp
        else:
            if totp_field:
                extra['fields'].remove(totp_field)
        return extra
    else:
        raise ValueError(f'extract_password_record_extra: V2 record type is expected')


def extract_audit_data(record):      # type: (vault.KeeperRecord) -> Optional[dict]
    url = ''
    if isinstance(record, vault.PasswordRecord):
        url = record.link
    elif isinstance(record, vault.TypedRecord):
        url_field = record.get_typed_field('url')
        if url_field:
            url = url_field.get_default_value(str)
    else:
        return

    title = record.title
    url = utils.url_strip(url)
    if len(title) + len(url) > 900:
        if len(title) > 900:
            title = title[:900]
        if len(url) > 900:
            url = url[:900]
    audit_data = {
        'title': title,
        'record_type': record.record_type
    }
    if url:
        audit_data['url'] = utils.url_strip(url)
    return audit_data


def extract_typed_field(field):     # type: (vault.TypedField) -> dict
    field_type = field.type or 'text'
    field_values = []
    default_value = None    # type: Union[None, str, int, Dict[str, str]]
    if field_type in record_types.RecordFields:
        rt = record_types.RecordFields[field_type]
        if rt.type in record_types.FieldTypes:
            ft = record_types.FieldTypes[rt.type]
            default_value = ft.value
    if field.value:
        values = field.value
        if isinstance(values, (str, int, dict)):
            values = [values]
        elif isinstance(values, (set, tuple)):
            values = list(values)

        if isinstance(values, list):
            for value in values:
                if not value:
                    continue
                if default_value is not None:
                    if not isinstance(value, type(default_value)):
                        continue
                if isinstance(default_value, dict):
                    for key in default_value:
                        if key not in value:
                            value[key] = ''
                field_values.append(value)
    result = {
        'type': field_type,
        'label': field.label or '',
        'value': field_values
    }
    if field.required is True:
        result['required'] = True
    return result


def extract_typed_record_data(record):      # type: (vault.TypedRecord) -> dict
    data = {
        'type': record.type_name or 'login',
        'title': record.title or '',
        'notes': record.notes or '',
        'fields': [],
        'custom': [],
    }
    for field in record.fields:
        data['fields'].append(extract_typed_field(field))
    for field in record.custom:
        data['custom'].append(extract_typed_field(field))
    return data


def extract_typed_record_refs(record):  # type: (vault.TypedRecord) -> Set[str]
    refs = set()
    for field in itertools.chain(record.fields, record.custom):
        if field.type in {'fileRef', 'addressRef', 'cardRef', 'recordRef'}:
            if not isinstance(field.value, list):
                continue
            for ref in field.value:
                if isinstance(ref, str):
                    refs.add(ref)
        elif field.type == 'script':
            if not isinstance(field.value, list):
                continue
            for script in field.value:
                if not isinstance(script, dict):
                    continue
                if 'fileRef' in script:
                    ref = script['fileRef']
                    if isinstance(ref, str):
                        refs.add(ref)

    return refs


class TypedRecordFacade(abc.ABC):
    def __init__(self):
        self.record = None  # type: Optional[vault.TypedRecord]

    @abc.abstractmethod
    def _get_facade_type(self):
        pass

    def assign_record(self, record):  # type: (vault.TypedRecord) -> None
        if not record.record_type:
            record.type_name = self._get_facade_type()
        self.record = record

    def get_custom_field(self, name):
        return next((x.get_default_value(str) for x in self.record.custom if x.label.lower() == name.lower()), '')

    @property
    def title(self):  # type: () -> Optional[str]
        if self.record:
            return self.record.title

    @title.setter
    def title(self, value):   # type: (str) -> None
        if self.record:
            self.record.title = value

    @property
    def notes(self):  # type: () -> Optional[str]
        if self.record:
            return self.record.notes

    @notes.setter
    def notes(self, value):   # type: (str) -> None
        if self.record:
            self.record.notes = value


class FileRefFacade(TypedRecordFacade, abc.ABC):
    def __init__(self):
        TypedRecordFacade.__init__(self)
        self._file_ref_field = None   # type: Optional[vault.TypedField]

    def assign_record(self, record):
        super(FileRefFacade, self).assign_record(record)
        if isinstance(record, vault.TypedRecord):
            self._file_ref_field = self.record.get_typed_field('fileRef')
            if self._file_ref_field is None:
                self._file_ref_field = vault.TypedField.new_field('fileRef', [])
                record.fields.append(self._file_ref_field)
        else:
            self._file_ref_field = None

    @property
    def file_ref(self):
        if self._file_ref_field:
            return self._file_ref_field.value


class ServerFacade(TypedRecordFacade, abc.ABC):
    def __init__(self):
        TypedRecordFacade.__init__(self)
        self.host_field = None   # type: Optional[vault.TypedField]
        self.login_field = None

    def assign_record(self, record):
        super(ServerFacade, self).assign_record(record)
        self.host_field = self.record.get_typed_field('host')
        self.login_field = self.record.get_typed_field('login')

    @property
    def host_name(self):
        if self.host_field:
            host_value = self.host_field.get_default_value(value_type=dict)
            if host_value:
                host = host_value.get('hostName')
                if isinstance(host, str):
                    return host

    @property
    def port(self):
        if self.host_field:
            host_value = self.host_field.get_default_value(value_type=dict)
            if host_value:
                port = host_value.get('port')
                if isinstance(port, str):
                    return port

    @property
    def login(self):
        if self.login_field:
            return self.login_field.get_default_value(value_type=str)


class SshKeysFacade(ServerFacade):
    def __init__(self):
        ServerFacade.__init__(self)
        self.passphrase_field = None  # type: Optional[vault.TypedField]
        self.key_pair_field = None    # type: Optional[vault.TypedField]

    def _get_facade_type(self):
        return 'sshKeys'

    def assign_record(self, record):
        super(SshKeysFacade, self).assign_record(record)
        self.passphrase_field = self.record.get_typed_field('password', 'passphrase')
        self.key_pair_field = self.record.get_typed_field('keyPair')

    @property
    def private_key(self):
        if self.key_pair_field:
            field_value = self.key_pair_field.get_default_value(value_type=dict)
            if field_value:
                key = field_value.get('privateKey')
                if isinstance(key, str):
                    return key

    @property
    def public_key(self):
        if self.key_pair_field:
            field_value = self.key_pair_field.get_default_value(value_type=dict)
            if field_value:
                key = field_value.get('publicKey')
                if isinstance(key, str):
                    return key

    @property
    def passphrase(self):
        if self.passphrase_field:
            return self.passphrase_field.get_default_value(value_type=str)


class ServerCredentialsFacade(ServerFacade):
    def __init__(self):
        ServerFacade.__init__(self)
        self.password_field = None  # type: Optional[vault.TypedField]

    def _get_facade_type(self):
        return 'serverCredentials'

    def assign_record(self, record):
        super(ServerCredentialsFacade, self).assign_record(record)
        self.password_field = self.record.get_typed_field('password')

    @property
    def password(self):
        if self.password_field:
            return self.password_field.get_default_value(value_type=str)


class DatabaseCredentialsFacade(ServerCredentialsFacade):
    def __init__(self):
        ServerCredentialsFacade.__init__(self)
        self.database_type_field = None   # type: Optional[vault.TypedField]

    def _get_facade_type(self):
        return 'databaseCredentials'

    def assign_record(self, record):
        super(DatabaseCredentialsFacade, self).assign_record(record)
        self.database_type_field = self.record.get_typed_field('text', 'type')

    @property
    def database_type(self):
        if self.database_type_field:
            return self.database_type_field.get_default_value(value_type=str)


class LoginFacade(FileRefFacade, abc.ABC):
    def __init__(self):
        FileRefFacade.__init__(self)
        self._login_field = None      # type: Optional[vault.TypedField]
        self._password_field = None   # type: Optional[vault.TypedField]
        self._url = None              # type: Optional[vault.TypedField]

    def assign_record(self, record):
        super(FileRefFacade, self).assign_record(record)
        if record:
            self._login_field = self.record.get_typed_field('login')
            if self._login_field is None:
                self._login_field = vault.TypedField.new_field('login', '')
                record.fields.append(self._login_field)
            self._password_field = self.record.get_typed_field('password')
            if self._password_field is None:
                self._password_field = vault.TypedField.new_field('password', '')
                record.fields.append(self._password_field)
            self._url = self.record.get_typed_field('url')
            if self._url is None:
                self._url = vault.TypedField.new_field('url', '')
                record.fields.append(self._url)
        else:
            self._login_field = None
            self._password_field = None
            self._url = None

    def _get_facade_type(self):
        return 'login'

    @property
    def login(self):
        return self._login_field.get_default_value(str) if self._login_field else ''

    @login.setter
    def login(self, value):
        if self._login_field:
            holder = self._login_field.value
            if isinstance(holder, list):
                if len(holder) > 0:
                    holder[0] = value
                else:
                    holder.append(value)

    @property
    def password(self):
        return self._password_field.get_default_value(str) if self._password_field else ''

    @password.setter
    def password(self, value):
        if self._password_field:
            holder = self._password_field.value
            if isinstance(holder, list):
                if len(holder) > 0:
                    holder[0] = value
                else:
                    holder.append(value)

    @property
    def url(self):
        return self._url.get_default_value(str) if self._url else ''

    @url.setter
    def url(self, value):
        if self._url:
            holder = self._url.value
            if isinstance(holder, list):
                if len(holder) > 0:
                    holder[0] = value
                else:
                    holder.append(value)
