import glob
import os
from contracting.client import ContractingClient
from cilantro_ee.core.logger.base import get_logger
from cilantro_ee.constants import conf
import cilantro_ee
import json

log = get_logger("sync")

# need to refactor this code of vkbook
PUBLIC_JSON_DIR = os.path.dirname(cilantro_ee.__path__[-1]) + '/constitutions/public'


def read_public_constitution(filename) -> dict:
    fpath = PUBLIC_JSON_DIR + '/' + filename
    assert os.path.exists(fpath), "No public constitution file found at path {}".format(fpath)
    with open(fpath) as f:
        return json.load(f)


def contract_name_from_file_path(p: str) -> str:
    directories = p.split('/')
    filename = directories[-1]

    name_and_file_extention = filename.split('.')
    name = name_and_file_extention[0]

    return name


def contracts_for_directory(path, extension, directory=os.path.dirname(__file__)):
    dir_path = os.path.join(directory, path) + '/' + extension
    contracts = glob.glob(dir_path)
    return contracts


def sync_genesis_contracts(genesis_path: str='genesis',
                           extension: str='*.s.py',
                           exclude=['vkbook'],
                           directory=os.path.dirname(__file__)):

    # Direct database writing of all contract files in the 'genesis' folder
    # direct_contracts = contracts_for_directory(direct_path, extension)
    # explicitly submit the submission contract
    submission_file = directory + '/submission.s.py'
    client = ContractingClient(submission_filename=submission_file)

    genesis_contracts = contracts_for_directory(genesis_path, extension, directory=directory)

    for contract in genesis_contracts:
        name = contract_name_from_file_path(contract)
        if name in exclude:
            continue

        if client.raw_driver.get_contract(name) is None:
            with open(contract) as f:
                code = f.read()

            client.submit(code, name=name)


def submit_contract_with_construction_args(name, directory=os.path.dirname(__file__), args={}):
    file = directory + '/genesis/{}.s.py'.format(name)

    submission_file = os.path.dirname(__file__) + '/submission.s.py'
    client = ContractingClient(submission_filename=submission_file)

    with open(file) as f:
        code = f.read()
        # log.debug('code {}'.format(code))
        # log.debug('name {}'.format(name))
        # log.debug('args {}'.format(args))
        client.submit(code, name=name, constructor_args=args)

    client.raw_driver.commit()


def get_masternodes_and_delegates_from_constitution(file=conf.CONSTITUTION_FILE):
    book = read_public_constitution(file)
    masternodes = [node['vk'] for node in book['masternodes']]
    delegates = [node['vk'] for node in book['delegates']]
    return masternodes, delegates

def submit_vkbook(vkbook_args: dict, overwrite=False):
    if not overwrite:
        c = ContractingClient()
        contract = c.get_contract('vkbook')
        if contract is not None:
            return

    submit_contract_with_construction_args('vkbook', args=vkbook_args)

def extract_sub_dict_values(book, key):
    if key in book:
        sb = book[key]
        vk_list = sb['vk_list'] if 'vk_list' in sb else []
        num_vks = len(vk_list)
        min_quorum = sb['min_quorum'] if 'min_quorum' in sb else num_vks
        if min_quorum > num_vks:
            log.warning(f"min quorum {min_quorum} is larger than number of vks"
                        f" {num_vks} for {key}. Reducing it to num of vks")
            min_quorum = num_vks
    else:
        vk_list = []
        min_quorum = 0
    return vk_list, min_quorum
  
def extract_vk_args(book):
    book['masternodes'], book['masternode_min_quorum'] = \
                              extract_sub_dict_values(book, 'masternodes')
    book['delegates'], book['delegate_min_quorum'] = \
                              extract_sub_dict_values(book, 'delegates')
    book['witnesses'], book['witness_min_quorum'] = \
                              extract_sub_dict_values(book, 'witnesses')
    book['notifiers'], book['notifier_min_quorum'] = \
                              extract_sub_dict_values(book, 'notifiers')
    book['schedulers'], book['scheduler_min_quorum'] = \
                              extract_sub_dict_values(book, 'schedulers')

def seed_vkbook(file=conf.CONSTITUTION_FILE, overwrite=False):
    book = read_public_constitution(file)
    extract_vk_args(book)
    submit_vkbook(book, overwrite)
