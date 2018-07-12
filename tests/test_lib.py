"""Test objects in module."""

import os
import sysconfig
import subprocess
import textwrap

import pytest

from sphinxcontrib.versioning.lib import Config, TempEnv


def test_config():
    """Test Config."""
    config = Config()
    config.update(dict(invert=True, overflow=('-D', 'key=value'), root_ref='master', verbose=1))

    # Verify values.
    assert config.banner_main_ref == 'master'
    assert config.greatest_tag is False
    assert config.invert is True
    assert config.overflow == ('-D', 'key=value')
    assert config.root_ref == 'master'
    assert config.verbose == 1
    assert repr(config) == ("<sphinxcontrib.versioning.lib.Config "
                            "_program_state={}, verbose=1, root_ref='master', overflow=('-D', 'key=value')>")

    # Verify iter.
    actual = sorted(config)
    expected = [
        ('banner_greatest_tag', False),
        ('banner_main_ref', 'master'),
        ('banner_recent_tag', False),
        ('chdir', None),
        ('git_root', None),
        ('greatest_tag', False),
        ('grm_exclude', tuple()),
        ('install_versions', False),
        ('invert', True),
        ('local_conf', None),
        ('no_colors', False),
        ('no_local_conf', False),
        ('overflow', ('-D', 'key=value')),
        ('priority', None),
        ('push_remote', 'origin'),
        ('recent_tag', False),
        ('root_ref', 'master'),
        ('show_banner', False),
        ('sort', tuple()),
        ('verbose', 1),
        ('whitelist_branches', tuple()),
        ('whitelist_tags', tuple()),
    ]
    assert actual == expected

    # Verify contains, setitem, and pop.
    assert getattr(config, '_program_state') == dict()
    assert 'key' not in config
    config['key'] = 'value'
    assert getattr(config, '_program_state') == dict(key='value')
    assert 'key' in config
    assert config.pop('key') == 'value'
    assert getattr(config, '_program_state') == dict()
    assert 'key' not in config
    assert config.pop('key', 'nope') == 'nope'
    assert getattr(config, '_program_state') == dict()
    assert 'key' not in config

    # Test exceptions.
    with pytest.raises(AttributeError) as exc:
        config.update(dict(unknown=True))
    assert exc.value.args[0] == "'Config' object has no attribute 'unknown'"
    with pytest.raises(AttributeError) as exc:
        config.update(dict(_program_state=dict(key=True)))
    assert exc.value.args[0] == "'Config' object does not support item assignment on '_program_state'"
    with pytest.raises(AttributeError) as exc:
        config.update(dict(invert=False))
    assert exc.value.args[0] == "'Config' object does not support item re-assignment on 'invert'"

def test_temp_env(tmpdir):
    showenv_script = tmpdir.join('showenv.py')
    showenv_script.write(textwrap.dedent("""\
        import sys
        import sysconfig
        print(sys.prefix)
        print(sysconfig.get_path('purelib'))
    """))
    r = subprocess.check_output(['python', str(showenv_script)])
    if isinstance(r, bytes):
        r = r.decode('UTF-8')
    current_env_prefix, current_env_lib = r.splitlines()

    def requirement_to_path(req):
        rname, rversion = req.split('==')
        rname = '_'.join(rname.split('-'))
        return '{}-{}.dist-info'.format(rname, rversion)

    with TempEnv() as temp_env:
        r = temp_env.run_python(str(showenv_script))
        temp_env_prefix, temp_env_lib = r.splitlines()

        assert temp_env_prefix != current_env_prefix
        assert temp_env_lib != current_env_lib
        assert os.path.commonpath([temp_env_prefix, temp_env_lib, temp_env.venv_path]) == temp_env.venv_path

        # Get packages installed in current environment and ensure they are not
        # available in the TempEnv
        local_requirements = temp_env.get_local_requirements()
        for req in local_requirements:
            req_name = req.split('==')[0]
            req_path = requirement_to_path(req)
            req_path = os.path.join(temp_env_lib, req_path)
            assert not os.path.exists(req_path)
            assert not temp_env.is_installed(req_name)

        # Install all packages from current environment in the venv and validate
        # their locations
        temp_env.clone_local_env()

        for req in local_requirements:
            req_name = req.split('==')[0]
            req_path = requirement_to_path(req)
            req_path = os.path.join(temp_env_lib, req_path)
            assert os.path.exists(req_path)
            assert temp_env.is_installed(req_name)

    assert not os.path.exists(temp_env_prefix)
    assert not os.path.exists(temp_env.name)

def test_temp_packages(local_py_package):
    local_path, pkg_data = local_py_package

    with TempEnv() as temp_env:
        with temp_env.pip_install_context(str(local_path)) as temp_pkg:
            assert temp_pkg.path == str(local_path)
            assert temp_pkg.script_name == str(pkg_data['pkg_files']['setup.py']['path'])
            assert temp_pkg.pkg_name == pkg_data['pkg_meta']['name']
            assert temp_pkg.is_installed
            assert temp_env.is_installed(pkg_data['pkg_meta']['name'])
            r = temp_env.run_python('-m pip show {}'.format(pkg_data['pkg_meta']['name']))
            pkg_name = None
            pkg_version = None
            for line in r.splitlines():
                if line.startswith('Name: '):
                    pkg_name = line.lstrip('Name: ')
                elif line.startswith('Version: '):
                    pkg_version = line.lstrip('Version: ')
            assert pkg_name == pkg_data['pkg_meta']['name']
            assert pkg_version == pkg_data['pkg_meta']['version']
        assert not temp_pkg.is_installed
        assert not temp_env.is_installed(pkg_data['pkg_meta']['name'])
