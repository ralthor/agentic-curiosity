from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from .env import env_bool, env_list, load_env_file


class EnvTests(SimpleTestCase):
    def test_load_env_file_reads_values_without_overwriting_existing_env(self):
        with TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            {'PRESERVE_ME': 'original'},
            clear=True,
        ):
            env_file = Path(tmpdir) / '.env'
            env_file.write_text(
                '\n'.join(
                    [
                        '# comment',
                        'FOO=bar',
                        'PRESERVE_ME=updated',
                        'QUOTED="hello world"',
                    ]
                ),
                encoding='utf-8',
            )

            load_env_file(env_file)

            self.assertEqual(os.environ['FOO'], 'bar')
            self.assertEqual(os.environ['QUOTED'], 'hello world')
            self.assertEqual(os.environ['PRESERVE_ME'], 'original')

    def test_env_bool_and_env_list_parse_expected_values(self):
        with patch.dict(
            os.environ,
            {
                'BOOL_TRUE': 'true',
                'BOOL_FALSE': '0',
                'LIST_VALUE': 'localhost, 127.0.0.1, , example.com ',
            },
            clear=True,
        ):
            self.assertTrue(env_bool('BOOL_TRUE'))
            self.assertFalse(env_bool('BOOL_FALSE', default=True))
            self.assertEqual(env_list('LIST_VALUE'), ['localhost', '127.0.0.1', 'example.com'])
            self.assertEqual(env_list('MISSING', default=['fallback']), ['fallback'])
