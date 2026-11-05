"""Protect referenced/distinct/animated normal data during optional compaction."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

tree=ast.parse(Path('assets/Import_Existing_USD.py').read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='compact_redundant_usd_normals')

class Vectors:
    def __init__(self,values):self.values=list(values)
    def __len__(self):return len(self.values)//3
    def foreach_get(self,name,out):
        assert name=='vector'
        for i,v in enumerate(self.values):out[i]=v
    def foreach_set(self,name,values):self.values[:]=values

class Attributes(dict):
    def remove(self,attr):del self['normals']
    def new(self,name,type,domain):
        attr=NS(name=name,data_type=type,domain=domain,data=Vectors([0.0]*9));self[name]=attr;return attr

def run(source=None,referenced=False,shared=False,animated=False,simulate_mismatch=False,dynamic_name=False):
    native=[0.,0.,1.]*3
    attrs=Attributes(normals=NS(data=Vectors(source if source is not None else native),domain='CORNER',data_type='FLOAT_VECTOR'))
    class CornerNormals(Vectors):
        def foreach_get(self,name,out):
            self.values=([1.,0.,0.]*3 if simulate_mismatch and 'normals' not in attrs else native)
            super().foreach_get(name,out)
    mesh=NS(as_pointer=lambda:1,users=2 if shared else 1,shape_keys=None,animation_data=None,
            has_custom_normals=True,attributes=attrs,corner_normals=CornerNormals(native))
    ob=NS(type='MESH',data=mesh,modifiers=[],animation_data=object() if animated else None)
    nodes=[NS(attribute_name='normals' if referenced else 'Cd',inputs=[NS(type='STRING',is_linked=True)] if dynamic_name else [])]
    scope={'log':lambda *a:None,'bpy':NS(data=NS(materials=[NS(use_nodes=True,node_tree=NS(nodes=nodes))],node_groups=[]),context=NS(scene=NS(objects=[ob])))}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<normals>','exec'),scope)
    saved=scope['compact_redundant_usd_normals']()
    return saved,attrs

saved,attrs=run();assert saved==36 and 'normals' not in attrs
for case in ({'referenced':True},{'shared':True},{'animated':True},{'source':[1.,0.,0.]*3},{'simulate_mismatch':True},{'dynamic_name':True}):
    saved,attrs=run(**case);assert saved==0 and 'normals' in attrs,case
assert list(run(simulate_mismatch=True)[1]['normals'].data.values)==[0.,0.,1.]*3
print('Normal compaction preserves referenced, distinct, animated/shared data and restores on shading mismatch.')
