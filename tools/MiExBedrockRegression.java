import java.nio.file.*;
import java.lang.reflect.Method;
import java.util.*;
import com.google.gson.*;
import nl.bramstout.mcworldexporter.expression.*;
import nl.bramstout.mcworldexporter.expression.ExprValue.ExprValueDict;
import nl.bramstout.mcworldexporter.nbt.*;
import nl.bramstout.mcworldexporter.resourcepack.ResourcePacks;
import nl.bramstout.mcworldexporter.resourcepack.java.ResourcePackJavaEdition;
import nl.bramstout.mcworldexporter.model.Model;
import nl.bramstout.mcworldexporter.model.builtins.BuiltInModel;
import nl.bramstout.mcworldexporter.translation.BlockTranslation.BlockTranslatorManager;

/** Semantic checks using the actual pinned MiEx evaluator and reader overlay. */
public final class MiExBedrockRegression {
    static final String[] COLORS = {"white","orange","magenta","light_blue","yellow","lime","pink","gray","light_gray","cyan","purple","blue","brown","green","red","black"};
    static ExprContext evaluate(String file, String name, NbtTagCompound properties) throws Exception {
        JsonObject model = JsonParser.parseString(Files.readString(Path.of("assets", file))).getAsJsonObject();
        ExprContext ctx = new ExprContext(name, properties, true, -7,82,29,-7f,82f,29f,0f,0f,0f,
            null,new ExprValue(new ExprValueDict()),ExprValue.VALUE_BUILTINS,new HashMap<>(),new HashMap<>());
        JsonArray handlers=new JsonArray();
        if(model.get("handler").isJsonArray()) handlers=model.getAsJsonArray("handler");
        else handlers.add(model.get("handler"));
        for(JsonElement value:handlers) {
            JsonObject handler=value.getAsJsonObject();
            if(handler.has("condition") && !ExprParser.parseMultiExpression(handler.get("condition").getAsString()).eval(ctx).asBool())continue;
            if(handler.has("variables"))for(JsonElement line:handler.getAsJsonArray("variables"))
                ExprParser.parseMultiExpression(line.getAsString()).eval(ctx);
        }
        return ctx;
    }
    static NbtTagCompound props() { return NbtTagCompound.newNonPooledInstance(""); }
    static void expect(Object actual, Object expected) {
        if(!Objects.equals(actual,expected)) throw new AssertionError("Expected " + expected + ", got " + actual);
    }
    static Model bake(String file,String name,NbtTagCompound properties) throws Exception {
        BuiltInModel handler=new BuiltInModel();
        handler.parse(JsonParser.parseString(Files.readString(Path.of("assets",file))).getAsJsonObject());
        Model model=new Model(name,null,handler.doubleSided,false);
        ExprContext ctx=new ExprContext(name,properties,false,0,64,0,0f,64f,0f,0f,0f,0f,
            model,new ExprValue(new ExprValueDict()),ExprValue.VALUE_BUILTINS,handler.localGenerators,handler.localFunctions);
        handler.rootPart.eval(ctx);
        return model;
    }
    static Set<String> textures(Model model) {
        Set<String> result=new HashSet<>();
        for(var face:model.getFaces())result.add(model.getTexture(face.getTexture()));
        return result;
    }
    static void checkLeatherDye() throws Exception {
        JsonObject attachment=JsonParser.parseString(Files.readString(Path.of("assets/Bedrock_Armor_Leggings.json"))).getAsJsonObject();
        BuiltInModel handler=new BuiltInModel();handler.parse(attachment.getAsJsonObject("rightLeg"));
        NbtTagCompound item=props();item.addElement(NbtTagInt.newNonPooledInstance("customColor",0x22bb55));
        Model model=new Model("leather fixture",null,true,false);
        ExprContext ctx=new ExprContext("minecraft:leather_leggings",item,false,0,0,0,0,0,0,0,0,0,
            model,new ExprValue(new ExprValueDict()),ExprValue.VALUE_BUILTINS,handler.localGenerators,handler.localFunctions);
        handler.rootPart.eval(ctx);
        if(model.getFaces().isEmpty() || !model.getFaces().get(0).hasVertexColor)throw new AssertionError("Leather dye discarded");
        var expected=new nl.bramstout.mcworldexporter.Color(0x22bb55);
        expect(model.getFaces().get(0).vertexColorR,expected.getR());
        expect(model.getFaces().get(0).vertexColorG,expected.getG());
        expect(model.getFaces().get(0).vertexColorB,expected.getB());
        // Mixing sidedness makes MiEx duplicate attachment faces in reverse,
        // causing coplanar artifacts on the equipped stand.
        Model stand=bake("Bedrock_Armor_Stand.json","minecraft:armor_stand",props());
        int expectedFaces=stand.getFaces().size()+model.getFaces().size();
        stand.addModel(model);
        expect(stand.getFaces().size(),expectedFaces);
        expect(stand.isDoubleSided(),true);
    }
    static void checkDetails() throws Exception {
        Class<?> reader=Class.forName("nl.bramstout.mcworldexporter.world.bedrock.ChunkBedrock");
        Method details=reader.getDeclaredMethod("normalizeBedrockDetails",String.class,NbtTagCompound.class,BlockTranslatorManager.class);
        details.setAccessible(true);
        for(String plantName:new String[]{"pink_tulip","red_tulip","azure_bluet","dead_bush","oak_sapling","open_eyeblossom"}) {
            NbtTagCompound tag=props(),plant=props();plant.setName("PlantBlock");
            plant.addElement(NbtTagString.newNonPooledInstance("name","minecraft:"+plantName));tag.addElement(plant);
            expect(details.invoke(null,"minecraft:potted_closed_eyeblossom",tag,new BlockTranslatorManager()),"minecraft:potted_"+plantName);
        }
        NbtTagCompound emptyPot=props();emptyPot.addElement(NbtTagString.newNonPooledInstance("id","FlowerPot"));
        expect(details.invoke(null,"minecraft:potted_closed_eyeblossom",emptyPot,new BlockTranslatorManager()),"minecraft:flower_pot");
        expect(details.invoke(null,"minecraft:potted_poppy",props(),new BlockTranslatorManager()),"minecraft:potted_poppy");
        String[] names={"skeleton_skull","wither_skeleton_skull","zombie_head","player_head","creeper_head","dragon_head","piglin_head"};
        for(int type=0;type<names.length;type++) {
            NbtTagCompound tag=props();
            tag.addElement(NbtTagInt.newNonPooledInstance("miex_legacy_skull",1));
            tag.addElement(NbtTagByte.newNonPooledInstance("SkullType",(byte)type));
            tag.addElement(NbtTagFloat.newNonPooledInstance("Rotation",90f));
            expect(details.invoke(null,"minecraft:dragon_head",tag,new BlockTranslatorManager()),"minecraft:"+names[type]);
            expect(tag.get("rotation").asString(),"4");
            if(type==3)continue; // Player profiles can require external skin lookup.
            Model model=bake("Bedrock_Skulls.json","minecraft:"+names[type],tag);
            expect(model.getFaces().size(),type==5?42:type==6?36:6);
            if(type==1)expect(textures(model),Set.of("minecraft:entity/skeleton/wither_skeleton"));
        }
        NbtTagCompound modern=props();modern.addElement(NbtTagInt.newNonPooledInstance("SkullType",0));
        expect(details.invoke(null,"minecraft:wither_skeleton_skull",modern,new BlockTranslatorManager()),"minecraft:wither_skeleton_skull");
        String[] directions={"north","east","south","west"};
        float[] angles={180f,270f,0f,90f};
        for(int i=0;i<directions.length;i++) {
            NbtTagCompound wall=props();
            wall.addElement(NbtTagString.newNonPooledInstance("facing",directions[i]));
            wall.addElement(NbtTagString.newNonPooledInstance("rotation","4"));
            expect(evaluate("Bedrock_Skulls.json","minecraft:dragon_wall_head",wall).variables.get("rotY").asFloat(),angles[i]);
        }
        NbtTagCompound pot=props();
        pot.addElement(NbtTagList.newNonPooledInstance("sherds",new NbtTag[]{
            NbtTagString.newNonPooledInstance("","minecraft:archer_pottery_sherd"),
            NbtTagString.newNonPooledInstance("","minecraft:arms_up_pottery_sherd"),
            NbtTagString.newNonPooledInstance("","minecraft:brick"),
            NbtTagString.newNonPooledInstance("","minecraft:flow_pottery_sherd")}));
        Model potModel=bake("Bedrock_Decorated_Pots.json","minecraft:decorated_pot",pot);
        expect(potModel.getFaces().size(),18);
        if(!textures(potModel).containsAll(Set.of("minecraft:entity/decorated_pot/archer_pottery_pattern",
            "minecraft:entity/decorated_pot/arms_up_pottery_pattern","minecraft:entity/decorated_pot/flow_pottery_pattern")))throw new AssertionError("Missing pot pattern textures");
        expect(bake("Bedrock_Conduits.json","minecraft:conduit",props()).getFaces().size(),6);
        // Supply a minimal real Java model to exercise the generator's API.
        // A misspelled model argument silently drops the entire table base.
        Path fixture=Files.createTempDirectory("miex-book-model-");
        var active=ResourcePacks.getActiveResourcePacks();var previous=new ArrayList<>(active);
        try {
            JsonObject base=new JsonObject(),element=new JsonObject(),faces=new JsonObject();
            base.add("textures",JsonParser.parseString("{\"all\":\"minecraft:block/enchanting_table_top\"}"));
            element.add("from",JsonParser.parseString("[0,0,0]"));element.add("to",JsonParser.parseString("[16,12,16]"));
            for(String direction:new String[]{"north","south","east","west","up","down"})
                faces.add(direction,JsonParser.parseString("{\"texture\":\"#all\"}"));
            element.add("faces",faces);JsonArray elements=new JsonArray();elements.add(element);base.add("elements",elements);
            Path file=fixture.resolve("assets/minecraft/models/block/enchanting_table.json");Files.createDirectories(file.getParent());Files.writeString(file,base.toString());
            active.clear();active.add(new ResourcePackJavaEdition(fixture.toFile()));
            Model table=bake("Bedrock_Enchanting_Table.json","minecraft:enchanting_table",props());
            expect(table.getFaces().size(),36);
            if(!textures(table).containsAll(Set.of("minecraft:block/enchanting_table_top","minecraft:entity/enchantment/enchanting_table_book")))throw new AssertionError("Table base/book missing: "+textures(table));
        } finally {
            active.clear();active.addAll(previous);
            try(var paths=Files.walk(fixture)){for(Path path:paths.sorted(Comparator.reverseOrder()).toList())Files.delete(path);}
        }
        Method armor=reader.getDeclaredMethod("normalizeBedrockArmorStand",String.class,NbtTagCompound.class);armor.setAccessible(true);
        NbtTagCompound stand=props(),item=props(),itemTag=props();
        item.addElement(NbtTagString.newNonPooledInstance("Name","minecraft:leather_leggings"));
        item.addElement(NbtTagByte.newNonPooledInstance("Count",(byte)1));
        itemTag.setName("tag");itemTag.addElement(NbtTagInt.newNonPooledInstance("customColor",0x22bb55));item.addElement(itemTag);
        stand.addElement(NbtTagList.newNonPooledInstance("Armor",new NbtTag[]{props(),props(),item,props()}));
        armor.invoke(null,"minecraft:armor_stand",stand);
        NbtTagCompound legs=(NbtTagCompound)((NbtTagCompound)stand.get("equipment")).get("legs");
        expect(legs.get("id").asString(),"minecraft:leather_leggings");expect(legs.get("customColor").asInt(),0x22bb55);
        if(stand.get("Armor")==null)throw new AssertionError("Original Bedrock equipment discarded");
        for(int pose=0;pose<13;pose++) {
            NbtTagCompound tag=props(),p=props();p.setName("Pose");p.addElement(NbtTagInt.newNonPooledInstance("PoseIndex",pose));tag.addElement(p);
            ExprContext ctx=evaluate("Bedrock_Armor_Stand.json","minecraft:armor_stand",tag);
            expect(ctx.variables.get("poseIndex").asInt(),(long)pose);
            expect(bake("Bedrock_Armor_Stand.json","minecraft:armor_stand",tag).getFaces().size(),66);
            if(pose==1)expect(ctx.variables.get("leftArmRotX").asFloat(),0f);
        }
        NbtTagCompound small=props();small.addElement(NbtTagByte.newNonPooledInstance("Small",(byte)1));
        expect(evaluate("Bedrock_Armor_Stand.json","minecraft:armor_stand",small).variables.get("scale").asFloat(),0.5f);
    }
    static void checkPartialPackFallbacks() throws Exception {
        // MiEx puts extracted world packs above BlenderEEVEE. A pack which
        // replaces one block must not switch all remaining beds to Java UVs.
        Path root=Files.createTempDirectory("miex-partial-pack-");
        String bed="assets/minecraft/textures/entity/bed/white.png";
        String shulker="assets/minecraft/textures/entity/shulker/shulker.png";
        String pole="assets/minecraft/textures/entity/banner_base.png";
        var packs=ResourcePacks.getActiveResourcePacks();
        var previous=new ArrayList<>(packs);
        try {
            for(String name:new String[]{"world","BlenderEEVEE","base_resource_pack"}) {
                Path folder=root.resolve(name);
                for(String texture:new String[]{bed,shulker,pole}) {
                    if(name.equals("world") && !texture.equals(shulker))continue;
                    Path file=folder.resolve(texture);
                    Files.createDirectories(file.getParent());
                    Files.writeString(file,"texture selection fixture: "+name);
                }
            }
            packs.clear();
            for(String name:new String[]{"world","BlenderEEVEE","base_resource_pack"})
                packs.add(new ResourcePackJavaEdition(root.resolve(name).toFile()));
            expect(ResourcePacks.getTexture("minecraft:entity/bed/white").toPath(),root.resolve("BlenderEEVEE").resolve(bed));
            expect(ResourcePacks.getTexture("minecraft:entity/shulker/shulker").toPath(),root.resolve("world").resolve(shulker));
            expect(ResourcePacks.getTexture("minecraft:entity/banner_base").toPath(),root.resolve("BlenderEEVEE").resolve(pole));
        } finally {
            packs.clear();packs.addAll(previous);
            try(var paths=Files.walk(root)) {
                for(Path path:paths.sorted(Comparator.reverseOrder()).toList())Files.delete(path);
            }
        }
    }
    static void runChecks() throws Exception {
        checkPartialPackFallbacks();
        checkDetails();
        checkLeatherDye();
        Method normalize = Class.forName("nl.bramstout.mcworldexporter.world.bedrock.ChunkBedrock")
            .getDeclaredMethod("normalizeBedrockBanner",String.class,NbtTagCompound.class);
        normalize.setAccessible(true);
        for(int dye=0;dye<16;dye++) {
            NbtTagCompound bed=props();
            bed.addElement(NbtTagByte.newNonPooledInstance("color",(byte)dye));
            bed.addElement(NbtTagByte.newNonPooledInstance("head_piece_bit",(byte)1));
            bed.addElement(NbtTagInt.newNonPooledInstance("direction",0));
            ExprContext ctx=evaluate("Bedrock_Beds.json","minecraft:black_bed",bed);
            expect(ctx.variables.get("color").asString(),COLORS[dye]);
            expect(ctx.variables.get("part").asString(),"head");
            NbtTagCompound banner=props();
            banner.addElement(NbtTagInt.newNonPooledInstance("Base",15-dye));
            NbtTagCompound pattern=props();
            pattern.addElement(NbtTagString.newNonPooledInstance("Pattern","bo"));
            pattern.addElement(NbtTagInt.newNonPooledInstance("Color",15-dye));
            banner.addElement(NbtTagList.newNonPooledInstance("Patterns",new NbtTag[]{pattern}));
            expect(normalize.invoke(null,"minecraft:black_wall_banner",banner),"minecraft:"+COLORS[dye]+"_wall_banner");
            expect(pattern.get("Color").asInt(),dye);
        }
        for(String name:new String[]{"shulker_box","undyed_shulker_box","white_shulker_box","black_shulker_box"}) {
            for(int direction=0;direction<6;direction++) {
                NbtTagCompound shulker=props();
                shulker.addElement(NbtTagInt.newNonPooledInstance("facing_direction",direction));
                ExprContext ctx=evaluate("Bedrock_Shulkers.json","minecraft:"+name,shulker);
                String expected=name.startsWith("white")?"shulker_white":name.startsWith("black")?"shulker_black":"shulker";
                expect(ctx.variables.get("type").asString(),expected);
                expect(ctx.variables.get("rotX").asFloat(),direction==0?180f:direction==1?0f:90f);
            }
        }
        NbtTagCompound ominous=props();
        ominous.addElement(NbtTagInt.newNonPooledInstance("Base",0));
        ominous.addElement(NbtTagInt.newNonPooledInstance("Type",1));
        expect(normalize.invoke(null,"minecraft:black_banner",ominous),"minecraft:white_banner");
        expect(((NbtTagList)ominous.get("Patterns")).getSize(),8);
        for(String wood:new String[]{"oak","birch","crimson","pale_oak"}) {
            for(int rotation=0;rotation<16;rotation++) {
                NbtTagCompound sign=props();sign.addElement(NbtTagInt.newNonPooledInstance("rotation",rotation));
                ExprContext s=evaluate("Bedrock_Signs.json","minecraft:"+wood+"_sign",sign);
                expect(s.variables.get("isWall").asBool(),false);
                expect(s.variables.get("modelName").asString(),"minecraft:block/"+wood+"_sign_rot_"+(rotation%4));
                for(int attached=0;attached<2;attached++) {
                    sign.addElement(NbtTagByte.newNonPooledInstance("attached_bit",(byte)attached));
                    s=evaluate("Bedrock_Hanging_Signs.json","minecraft:"+wood+"_hanging_sign",sign);
                    expect(s.variables.get("modelName").asString(),"minecraft:block/"+wood+"_hanging_sign"+(attached==1?"_attached":"")+"_rot_"+(rotation%4));
                }
            }
            for(int facing=2;facing<=5;facing++) {
                NbtTagCompound sign=props();sign.addElement(NbtTagInt.newNonPooledInstance("facing_direction",facing));
                ExprContext s=evaluate("Bedrock_Signs.json","minecraft:"+wood+"_wall_sign",sign);
                expect(s.variables.get("isWall").asBool(),true);
                expect(s.variables.get("modelName").asString(),"minecraft:block/"+wood+"_wall_sign");
                expect(s.variables.get("rotY").asFloat(),new float[]{180,0,90,270}[facing-2]);
            }
        }
        Method normalizeSign=normalize.getDeclaringClass().getDeclaredMethod("normalizeBedrockSign",String.class,NbtTagCompound.class);
        normalizeSign.setAccessible(true);
        NbtTagCompound sign=props(), back=props();
        back.setName("BackText");back.addElement(NbtTagString.newNonPooledInstance("Text","Back"));
        sign.addElement(back);sign.addElement(NbtTagString.newNonPooledInstance("Text","Front"));
        normalizeSign.invoke(null,"minecraft:oak_sign",sign);
        expect(((NbtTagCompound)sign.get("FrontText")).get("Text").asString(),"Front");
        expect(((NbtTagCompound)sign.get("BackText")).get("Text").asString(),"Back");
        expect(((NbtTagCompound)sign.get("FrontText")).get("IgnoreLighting"),null);
        NbtTagCompound frame=props();
        frame.addElement(NbtTagInt.newNonPooledInstance("x",-7));
        ExprContext ctx=evaluate("Bedrock_Beds.json","minecraft:bed",frame);
        expect(ExprParser.parseMultiExpression("thisEntity.state.x != null ? (0.5 + thisEntity.state.x) : 0.0").eval(ctx).asFloat(),-6.5f);
        expect(ExprParser.parseMultiExpression("thisEntity.state.z != null ? (0.5 + thisEntity.state.z) : 0.0").eval(ctx).asFloat(),0f);
        System.out.println("Pinned MiEx runtime: pots/plants, skull types, conduit geometry, armor equipment/poses, partial packs, dyes/patterns, shulkers, frames and signs passed.");
        // ChunkBedrock starts MiEx's periodic background cache cleanup thread.
        System.exit(0);
    }
    public static void main(String[] args) {
        try { runChecks(); }
        catch(Throwable ex) { ex.printStackTrace(); System.exit(1); }
    }
}
