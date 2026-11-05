"""Retain preview colors when shaders, viewports or edits can depend on them."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

tree = ast.parse(Path('assets/Import_Existing_USD.py').read_text())
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
          and n.name == 'remove_unused_usd_display_colors')


class Colors(dict):
    def remove(self, attr):
        del self[attr.name]


def run(reference=None, vertex_view=False, shared=False, edited=False,
        dynamic=False, painting=False, animated=False, library=False,
        animated_tree=False, scripted=False):
    colors = Colors(displayColor=NS(name='displayColor', domain='CORNER',
                                   data_type='FLOAT_COLOR', data=range(12)),
                    Cd=NS(name='Cd', data=[0.1, 0.2, 0.3]))
    mesh = NS(users=2 if shared else 1, shape_keys=None, animation_data=None,
              library=object() if library else None, color_attributes=colors)
    ob = NS(type='MESH', data=mesh, modifiers=[object()] if edited else [],
            animation_data=object() if animated else None,
            mode='VERTEX_PAINT' if painting else 'OBJECT')
    node = NS(type='SCRIPT' if scripted else ('VERTEX_COLOR' if reference in ('default', 'named') else 'ATTRIBUTE'),
              layer_name='' if reference == 'default' else ('displayColor' if reference == 'named' else 'Cd'),
              attribute_name='displayColor' if reference == 'attribute' else '',
              inputs=[NS(type='STRING', is_linked=dynamic,
                         default_value='displayColor' if reference == 'socket' else '')])
    space = NS(type='VIEW_3D', shading=NS(color_type='VERTEX' if vertex_view else 'TEXTURE'))
    bpy = NS(context=NS(scene=NS(objects=[ob])),
             data=NS(materials=[NS(use_nodes=True, node_tree=NS(nodes=[node],
                     animation_data=object() if animated_tree else None))],
                     node_groups=[], screens=[NS(areas=[NS(type='VIEW_3D', spaces=[space])])]))
    scope = dict(bpy=bpy, log=lambda *a: None)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<display-colors>', 'exec'), scope)
    saved = scope['remove_unused_usd_display_colors']()
    assert colors['Cd'].data == [0.1, 0.2, 0.3]
    return saved, colors


saved, colors = run()
assert saved == 192 and 'displayColor' not in colors
for case in ({'reference': 'default'}, {'reference': 'named'}, {'reference': 'attribute'},
             {'reference': 'socket'}, {'vertex_view': True}, {'shared': True},
             {'edited': True}, {'dynamic': True}, {'painting': True},
             {'animated': True}, {'library': True}, {'scripted': True}):
    saved, colors = run(**case)
    assert saved == 0 and 'displayColor' in colors, case
# MiEx animates image UVs. Numeric node animation cannot rename a color layer;
# dynamic string inputs and every named/default reader are still scanned.
saved, colors = run(animated_tree=True)
assert saved == 192 and 'displayColor' not in colors
print('USD preview-color cleanup retains shader/default/dynamic references, vertex views and edited meshes; Cd is untouched.')
