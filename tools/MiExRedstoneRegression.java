import java.io.File;
import java.nio.file.*;
import java.util.*;
import nl.bramstout.mcworldexporter.MCWorldExporter;
import nl.bramstout.mcworldexporter.Reference;
import nl.bramstout.mcworldexporter.model.BlockStateRegistry;
import nl.bramstout.mcworldexporter.nbt.*;
import nl.bramstout.mcworldexporter.resourcepack.*;
import nl.bramstout.mcworldexporter.resourcepack.java.ResourcePackJavaEdition;
import nl.bramstout.mcworldexporter.translation.BlockConnectionsTranslation;
import nl.bramstout.mcworldexporter.world.*;

/** Exercise actual MiEx connection rules for flat, rising and descending wires. */
public class MiExRedstoneRegression {
    static final String[] NAMES={"east","west","south","north"};
    static final int[][] OFFSETS={{1,0},{-1,0},{0,1},{0,-1}};
    static NbtTagCompound properties() {
        NbtTagCompound p=NbtTagCompound.newNonPooledInstance("");
        for(String name:NAMES)p.addElement(NbtTagString.newNonPooledInstance(name,"none"));
        p.addElement(NbtTagString.newNonPooledInstance("power","15"));return p;
    }
    static int block(String name,NbtTagCompound p) {
        return BlockRegistry.getIdForName("minecraft:"+name,p,0,new Reference<char[]>());
    }
    static class TestWorld extends World {
        Map<String,Integer> cells=new HashMap<>();
        TestWorld(){super(new File("."),"redstone-test",null);}
        void set(int x,int y,int z,int id){cells.put(x+","+y+","+z,id);}
        public void loadWorldSettings(){}public void findDimensions(){}public void findRegions(){}
        public void _unload(){}public void _pause(){}public void _unpause(){}
        public List<String> getRequiredResourcePacks(){return List.of();}
        public List<ResourcePackSource> getDependentResourcePacks(){return List.of();}
        public int getBlockId(int x,int y,int z,int layer){return cells.getOrDefault(x+","+y+","+z,0);}
        public void getBlockId(int x,int y,int z,LayeredBlock b){b.setLayerCount(1);b.setBlock(0,getBlockId(x,y,z,0));}
    }
    public static void main(String[] args) {
        Path temp=null;
        int exitCode=0;
        try {
            temp=Files.createTempDirectory("miex-redstone-regression-");
            Path rules=temp.resolve("translation/minecraft/bedrock/miex_block_connections.json");
            Files.createDirectories(rules.getParent());
            Files.copy(Path.of("assets/Bedrock_Block_Connections.json"),rules);
            // Only the air block's solidity is consulted by the rising rules.
            // This synthetic empty model avoids depending on game assets.
            Path states=temp.resolve("assets/minecraft/blockstates");Files.createDirectories(states);
            Files.writeString(states.resolve("air.json"),"{\"variants\":{}}");
            ResourcePacks.getActiveResourcePacks().add(new ResourcePackJavaEdition(temp.toFile()));
            var access=sun.misc.Unsafe.class.getDeclaredField("theUnsafe");access.setAccessible(true);
            var unsafe=(sun.misc.Unsafe)access.get(null);
            var instance=MCWorldExporter.class.getDeclaredField("instance");instance.setAccessible(true);
            Object app=unsafe.allocateInstance(MCWorldExporter.class);instance.set(null,app);
            var field=MCWorldExporter.class.getDeclaredField("world");field.setAccessible(true);
            TestWorld world=new TestWorld();field.set(app,world);
            var translations=new BlockConnectionsTranslation("bedrock");translations.load();
            var map=translations.getBlockConnections("minecraft:redstone_wire",0);
            if(map==null)throw new AssertionError("Redstone mappings were not loaded");
            int wire=block("redstone_wire",properties());
            if(BlockStateRegistry.getBakedStateForBlock(0,0,65,0,0,false,false).isSolidBlock())
                throw new AssertionError("Air fixture is unexpectedly solid");
            for(int code=0;code<256;code++) {
                world.cells.clear();world.set(0,64,0,wire);
                String[] expected=new String[4];int value=code,count=0,last=-1;
                for(int i=0;i<4;i++) {
                    int kind=value%4;value/=4;
                    expected[i]=kind==0?"none":kind==2?"up":"side";
                    if(kind!=0){count++;last=i;world.set(OFFSETS[i][0],kind==1?64:kind==2?65:63,OFFSETS[i][1],wire);}
                }
                if(count==1)expected[last^1]="side";
                NbtTagCompound p=properties();map.map("minecraft:redstone_wire",p,0,64,0,0);
                for(int i=0;i<4;i++)if(!p.get(NAMES[i]).asString().equals(expected[i]))
                    throw new AssertionError("Wire combination "+code+" "+NAMES[i]+": expected "+expected[i]+", got "+p.asJson());
            }
            for(String component:List.of("repeater","comparator"))for(int side=0;side<4;side++)for(String facing:NAMES) {
                world.cells.clear();world.set(0,64,0,wire);
                NbtTagCompound other=NbtTagCompound.newNonPooledInstance("");
                other.addElement(NbtTagString.newNonPooledInstance("facing",facing));
                world.set(OFFSETS[side][0],64,OFFSETS[side][1],block(component,other));
                NbtTagCompound p=properties();map.map("minecraft:redstone_wire",p,0,64,0,0);
                boolean connected=(side<2)==(facing.equals("east")||facing.equals("west"));
                for(int i=0;i<4;i++) {
                    String expected=connected&&(i/2==side/2)?"side":"none";
                    if(!p.get(NAMES[i]).asString().equals(expected))throw new AssertionError(component+" "+facing+" neighbor "+NAMES[side]+": "+p.asJson());
                }
            }
            System.out.println("Native MiEx redstone: 256 none/flat/rising/descending combinations and 32 repeater/comparator orientations passed.");
        } catch(Throwable error){error.printStackTrace();exitCode=1;}
        finally {
            if(temp!=null)try(var paths=Files.walk(temp)){
                for(Path path:paths.sorted(Comparator.reverseOrder()).toList())Files.delete(path);
            }catch(Exception error){throw new RuntimeException(error);}
        }
        System.exit(exitCode);
    }
}
