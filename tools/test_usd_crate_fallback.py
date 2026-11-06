"""The missing optional prototype helper must not disable Crate conversion."""
import importlib.util
import sys
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS
from unittest.mock import patch

script = Path('assets/Convert_USD_To_Crate.py').resolve()
spec = importlib.util.spec_from_file_location('crate_test', script)
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


class Layer:
    larger = False

    def __init__(self, path):
        self.path = Path(path)
        self.rootPrims = [NS(name='World')]
        self.subLayerPaths = ['./World_materials.usd']

    def Export(self, path, args):
        assert args == {'format': 'usdc'}
        Path(path).write_bytes(b'PXR-USDC' + (b'x' * 70000 if self.larger else b'data'))
        return True


pxr = ModuleType('pxr')
pxr.Sdf = NS(Layer=NS(FindOrOpen=Layer))
with tempfile.TemporaryDirectory(prefix='miex-crate-test-') as temp:
    root = Path(temp)
    for larger in (False, True):
        folder = root / str(larger)
        folder.mkdir()
        interface = folder / 'World.usd'
        interface.write_bytes(b'#usda 1.0\n')
        chunk = folder / 'chunk.usd'
        original = b'#usda 1.0\n' + b' ' * 65536
        chunk.write_bytes(original)
        report = folder / 'report.txt'
        Layer.larger = larger
        args = ['converter', '--', str(folder), str(report), 'World.usd']
        with patch.dict(sys.modules, {'pxr': pxr, 'Optimize_USD_Prototypes': None}), patch.object(sys, 'argv', args):
            converter.main()
        assert interface.read_bytes() == b'#usda 1.0\n'
        assert 'helper unavailable' in report.read_text()
        assert not list(folder.glob('*.crate_temp.usd'))
        if larger:
            assert chunk.read_bytes() == original
            assert '1 without size savings' in report.read_text()
        else:
            assert chunk.read_bytes() == b'PXR-USDCdata'
            assert '1 layers converted' in report.read_text()
            with patch.dict(sys.modules, {'pxr': pxr, 'Optimize_USD_Prototypes': None}), patch.object(sys, 'argv', args):
                converter.main()
            assert '1 already binary' in report.read_text()

    # A present helper remains supported. An import failure inside that helper
    # must not be mistaken for the optional module itself being absent.
    calls = []
    helper = ModuleType('Optimize_USD_Prototypes')
    helper.optimize_and_validate = lambda p: calls.append(p) or 'verified helper'
    with patch.dict(sys.modules, {'pxr': pxr, 'Optimize_USD_Prototypes': helper}), patch.object(sys, 'argv', args):
        converter.main()
    assert calls == [interface]
    assert report.read_text().startswith('verified helper\n')

    def missing_dependency(name):
        raise ModuleNotFoundError('Missing helper dependency', name='helper_dependency')

    del helper.optimize_and_validate
    helper.__getattr__ = missing_dependency
    with patch.dict(sys.modules, {'pxr': pxr, 'Optimize_USD_Prototypes': helper}), patch.object(sys, 'argv', args):
        try:
            converter.main()
        except ModuleNotFoundError as error:
            assert error.name == 'helper_dependency'
        else:
            raise AssertionError('An unrelated import error was swallowed')

print('Crate conversion retains missing-helper fallback, existing helpers, smaller-only replacement and repeat runs.')
