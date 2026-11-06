import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import com.google.gson.*;
import nl.bramstout.mcworldexporter.MCWorldExporter;
import nl.bramstout.mcworldexporter.Reference;
import nl.bramstout.mcworldexporter.expression.*;
import nl.bramstout.mcworldexporter.expression.ExprValue.ExprValueDict;
import nl.bramstout.mcworldexporter.model.*;
import nl.bramstout.mcworldexporter.model.builtins.BuiltInModel;
import nl.bramstout.mcworldexporter.nbt.*;
import nl.bramstout.mcworldexporter.resourcepack.ResourcePackSource;
import nl.bramstout.mcworldexporter.world.*;

/** Native MiEx checks against geometric fingerprints from the official Java client.
 * Client SHA1: 4e618f09a0c649dde3fdf829df443ce0b8831e65 (26.1.2).
 * DumpJavaStatues.java extracts the independent reference including UVs and winding.
 */
public class MiExJavaVisualRegression {
    static final String[] POSES={"standing","sitting","running","star"};
    static final String[] DIRECTIONS={"north","east","south","west"};
    static final String[][] EXPECTED={
        {"3e9db12998687ff13a73b8844b66b0510285c18825dfbdcc1c33c2db0c00a8fe","4bf44371078bff480d21ae3f687ed4a43677a4daecede85b5b172890f1ec13b3","e24c8d893e2246c8eb8bf8f52338ce8dd1b0a422dba79262299b1390cbdc029c","47307c9b7cd276c774580587565f6f72a129dd032c8ee97e4b7b68fbec3b6cd2"},
        {"5d74dfeb1edfb1cab577ac7069d5f511dea22490d3a1275d42e6c01fbc878250","dfad116faa6594076bbc86e6c00ed02b09c7ed18a70cd372c4544d7983a0c5dd","e0db64bb3326c7476f8ae65b8dfcd724315939f31a561fc08d8f1fd49eb803b1","afb273cdd4810b4d34f0bed2953b280e75d6b0306c87812f97ba660feda10a66"},
        {"e31ddd0fa6af064175fe7560f223a85b6464314015e3371a5754ccbc30165064","13dcab6e35f85a65707fba9759d4fe64da3c980c72373a37c187d8adfda2dec9","75aefc9d9a6b823f39ca5c5bfa39d875b609355671c1b601bb899b36dab8f056","c3ee3d3169305a4c7abf8dbc080875b3c1b07174e819c84fb4a635d276058f62"},
        {"be1721396077e93a7baf75d3bfc92456af4003bd30c57b1ff2abd7bed6b09132","70a93497e5d90c6aeae5672dd2dc5c08990d5607ef19bf49c4c560bfacf3268d","2a8cd133ade8fd4a24201ab4df381f1bec368520f5e7a63e4505b69310d746f0","df988f29448012783d8756486a7c0c2e2c1198ee537e763db4414a76780a53d0"}
    };
    static NbtTagCompound props(){return NbtTagCompound.newNonPooledInstance("");}
    static Model bake(String file,String name,NbtTagCompound properties)throws Exception {
        JsonObject doc=JsonParser.parseString(Files.readString(Path.of("assets",file))).getAsJsonObject();
        BuiltInModel h=new BuiltInModel();h.parse(doc);
        Model m=new Model(name,null,h.doubleSided,false);
        ExprContext c=new ExprContext(name,properties,doc.has("isLocationDependent")&&doc.get("isLocationDependent").getAsBoolean(),0,64,0,0f,64f,0f,0f,0f,0f,m,new ExprValue(new ExprValueDict()),ExprValue.VALUE_BUILTINS,h.localGenerators,h.localFunctions);
        h.rootPart.eval(c);return m;
    }
    static long quant(float value) {
        // Remove insignificant matrix float noise before 0.01-model-unit
        // reference quantization. UVs, per-face association and winding remain.
        return Math.round(Math.round((double)value*10000)/100.0);
    }
    static String fingerprint(Model model)throws Exception {
        List<String> rows=new ArrayList<>();float[] xyz=new float[12],uv=new float[8];
        for(var face:model.getFaces()) {
            face.getPoints(xyz);face.getUVs(uv);List<String> vertices=new ArrayList<>();
            for(int i=0;i<4;i++)vertices.add(quant(xyz[i*3])+","+quant(xyz[i*3+1])+","+quant(xyz[i*3+2])+","+quant(uv[i*2])+","+quant(uv[i*2+1]));
            String best=null;for(int rotation=0;rotation<4;rotation++) {
                List<String> shifted=new ArrayList<>();for(int i=0;i<4;i++)shifted.add(vertices.get((i+rotation)%4));String row=String.join(";",shifted);
                if(best==null||row.compareTo(best)<0)best=row;
            }rows.add(best);
        }
        Collections.sort(rows);return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(String.join("\n",rows).getBytes(StandardCharsets.UTF_8)));
    }
    static void statues()throws Exception {
        for(String wax:new String[]{"","waxed_"})for(String stage:new String[]{"","exposed_","weathered_","oxidized_"})
            for(int pose=0;pose<POSES.length;pose++)for(int dir=0;dir<DIRECTIONS.length;dir++) {
                NbtTagCompound properties=props();properties.addElement(NbtTagString.newNonPooledInstance("pose",POSES[pose]));properties.addElement(NbtTagString.newNonPooledInstance("facing",DIRECTIONS[dir]));
                Model m=bake("Java_Copper_Statues.json","minecraft:"+wax+stage+"copper_golem_statue",properties);
                if(!fingerprint(m).equals(EXPECTED[pose][dir]))throw new AssertionError("Native Java statue mismatch: "+POSES[pose]+" "+DIRECTIONS[dir]);
                String texture="minecraft:entity/copper_golem/copper_golem"+(stage.isEmpty()?"":"_"+stage.substring(0,stage.length()-1));
                for(var face:m.getFaces())if(!m.getTexture(face.getTexture()).equals(texture))throw new AssertionError("Wrong oxidation atlas");
            }
    }
    static class TestWorld extends World {
        Map<String,Integer> cells=new HashMap<>();
        TestWorld(){super(new File("."),"visual-test",null);}
        void set(int x,int y,int z,int id){cells.put(x+","+y+","+z,id);}
        public void loadWorldSettings(){}public void findDimensions(){}public void findRegions(){}public void _unload(){}public void _pause(){}public void _unpause(){}
        public List<String> getRequiredResourcePacks(){return List.of();}public List<ResourcePackSource> getDependentResourcePacks(){return List.of();}
        public int getBlockId(int x,int y,int z,int layer){return cells.getOrDefault(x+","+y+","+z,0);}
        public void getBlockId(int x,int y,int z,LayeredBlock b){b.setLayerCount(1);b.setBlock(0,getBlockId(x,y,z,0));}
    }
    static int block(String name,NbtTagCompound properties){return BlockRegistry.getIdForName("minecraft:"+name,properties,0,new Reference<char[]>());}
    static void conduits()throws Exception {
        // A minimal application/world fixture avoids starting MiEx's UI,
        // launcher discovery or network updater in this runtime regression.
        var access=sun.misc.Unsafe.class.getDeclaredField("theUnsafe");access.setAccessible(true);var unsafe=(sun.misc.Unsafe)access.get(null);
        var instance=MCWorldExporter.class.getDeclaredField("instance");instance.setAccessible(true);Object previous=instance.get(null),app=unsafe.allocateInstance(MCWorldExporter.class);
        var field=MCWorldExporter.class.getDeclaredField("world");field.setAccessible(true);TestWorld world=new TestWorld();field.set(app,world);instance.set(null,app);
        try {
            int water=block("water",props()),frame=block("prismarine",props());
            List<int[]> positions=new ArrayList<>();for(int x=-2;x<=2;x++)for(int y=-2;y<=2;y++)for(int z=-2;z<=2;z++)
                if(Math.max(Math.max(Math.abs(x),Math.abs(y)),Math.abs(z))==2&&(x==0||y==0||z==0))positions.add(new int[]{x,y,z});
            if(positions.size()!=42)throw new AssertionError("Wrong frame reference");
            for(int size:new int[]{0,15,16,42})for(boolean fullWater:new boolean[]{true,false}) {
                world.cells.clear();for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++)for(int z=-1;z<=1;z++)world.set(x,64+y,z,water);
                if(!fullWater)world.set(1,65,1,0);
                for(int i=0;i<size;i++){int[] pos=positions.get(i);world.set(pos[0],64+pos[1],pos[2],frame);}
                NbtTagCompound properties=props();properties.addElement(NbtTagString.newNonPooledInstance("waterlogged","true"));
                Model m=bake("Java_Conduits.json","minecraft:conduit",properties);boolean active=fullWater&&size>=16;
                if((m.getFaces().size()>6)!=active)throw new AssertionError("Wrong Java conduit activation: "+size+" water="+fullWater+" faces="+m.getFaces().size());
                if(active){boolean open=false;for(var face:m.getFaces())open|=m.getTexture(face.getTexture()).contains("open_eye");if(open!=(size==42))throw new AssertionError("Wrong conduit eye state");}
                NbtTagCompound bedrock=props();bedrock.addElement(NbtTagByte.newNonPooledInstance("Active",(byte)(active?1:0)));
                if(!fingerprint(m).equals(fingerprint(bake("Bedrock_Conduits.json","minecraft:conduit",bedrock))))throw new AssertionError("Edition conduit geometry differs for the same activation/frame state");
            }
        } finally {instance.set(null,previous);}
    }
    public static void main(String[] args) {
        try {
            for(String name:List.of("BlenderEEVEE_java","BlenderEEVEE_bedrock"))
                if(!new nl.bramstout.mcworldexporter.resourcepack.java.ResourcePackJavaEdition(new File(name)).getUUID().equals(name))throw new AssertionError("Edition pack UUID differs from command activation");
            statues();conduits();System.out.println("Java visual regression: 128 native statue pose/facing/material cases, edition pack IDs and conduit water/frame thresholds passed.");System.exit(0);
        }
        catch(Throwable ex){ex.printStackTrace();System.exit(1);}
    }
}
