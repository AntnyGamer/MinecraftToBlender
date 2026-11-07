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
import nl.bramstout.mcworldexporter.translation.BlockTranslation;

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
    static void checkPaletteAndEntityStates() throws Exception {
        Class<?> reader=Class.forName("nl.bramstout.mcworldexporter.world.bedrock.ChunkBedrock");
        Method palette=reader.getDeclaredMethod("translateBedrockPalette",String.class,NbtTagCompound.class,BlockTranslatorManager.class);
        Method merge=reader.getDeclaredMethod("mergeBedrockBlockEntity",NbtTagCompound.class,NbtTagCompound.class);
        Method details=reader.getDeclaredMethod("normalizeBedrockDetails",String.class,NbtTagCompound.class,BlockTranslatorManager.class);
        Method chest=reader.getDeclaredMethod("normalizeBedrockChest",String.class,NbtTagCompound.class,int.class,int.class);
        chest.setAccessible(true);
        palette.setAccessible(true);merge.setAccessible(true);details.setAccessible(true);
        Path root=Files.createTempDirectory("miex-translated-state-");
        var packs=ResourcePacks.getActiveResourcePacks();var previous=new ArrayList<>(packs);
        try {
            Path file=root.resolve("translation/minecraft/bedrock/miex_blocks.json");
            Files.createDirectories(file.getParent());
            try(var in=BlockTranslation.class.getResourceAsStream("/default_data/base_resource_pack/translation/minecraft/bedrock/miex_blocks.json")) {
                Files.copy(Objects.requireNonNull(in),file);
            }
            packs.clear();packs.add(new ResourcePackJavaEdition(root.toFile()));
            BlockTranslation translation=new BlockTranslation("bedrock");translation.load();
            BlockTranslatorManager translator=translation.getTranslator(0);
            String[] directions={"north","east","south","west"};
            for(String wax:new String[]{"","waxed_"})for(String stage:new String[]{"","exposed_","weathered_","oxidized_"}) {
                String name="minecraft:"+wax+stage+"copper_chest";
                for(int facing=0;facing<4;facing++) {
                    NbtTagCompound state=props();state.addElement(NbtTagString.newNonPooledInstance("minecraft:cardinal_direction",directions[facing]));
                    expect(palette.invoke(null,name,state,translator),name);
                    expect(state.get("type").asString(),"single");
                    for(int pair=-1;pair<=1;pair++) {
                        NbtTagCompound entity=(NbtTagCompound)state.copy();
                        // Cross chunk boundaries and negative world coordinates.
                        int x=-16,z=15;
                        if(pair!=0) {
                            entity.addElement(NbtTagInt.newNonPooledInstance("pairx",x+(facing%2==0?pair:0)));
                            entity.addElement(NbtTagInt.newNonPooledInstance("pairz",z+(facing%2==1?pair:0)));
                        }
                        chest.invoke(null,name,entity,x,z);
                        String type=pair==0?"single":((pair>0)==(facing<2)?"left":"right");
                        expect(entity.get("type").asString(),type);
                        Model model=bake("Bedrock_Copper_Chests.json",name,entity);
                        expect(model.getFaces().size(),18);
                        String texture="minecraft:entity/chest/copper"+(stage.isEmpty()?"":"_"+stage.substring(0,stage.length()-1))+(pair==0?"":"_"+type);
                        expect(textures(model),Set.of(texture));
                    }
                    String statue="minecraft:"+wax+stage+"copper_golem_statue";
                    Model model=bake("Bedrock_Copper_Statues.json",statue,state);
                    expect(model.getFaces().size(),54);
                    expect(textures(model),Set.of("minecraft:entity/copper_golem/copper_golem"+(stage.isEmpty()?"":"_"+stage.substring(0,stage.length()-1))));
                }
            }
            for(String axis:new String[]{"x","y","z"}) {
                NbtTagCompound chain=props();chain.addElement(NbtTagString.newNonPooledInstance("pillar_axis",axis));
                expect(palette.invoke(null,"minecraft:chain",chain,translator),"minecraft:chain");
                Path modern=root.resolve("assets/minecraft/blockstates/iron_chain.json");Files.createDirectories(modern.getParent());
                Files.writeString(modern,"{\"variants\":{}}");
                expect(palette.invoke(null,"minecraft:chain",chain,translator),"minecraft:iron_chain");
                Path legacy=modern.resolveSibling("chain.json");Files.writeString(legacy,"{\"variants\":{}}");
                expect(palette.invoke(null,"minecraft:chain",chain,translator),"minecraft:chain");
                Files.delete(legacy);Files.delete(modern);
            }
            for(int dye=0;dye<16;dye++) {
                NbtTagCompound state=props(),entity=props();
                state.addElement(NbtTagInt.newNonPooledInstance("direction",2));
                state.addElement(NbtTagByte.newNonPooledInstance("head_piece_bit",(byte)1));
                String name=(String)palette.invoke(null,"minecraft:bed",state,translator);
                expect(name,"minecraft:bed");
                entity.addElement(NbtTagByte.newNonPooledInstance("color",(byte)dye));
                merge.invoke(null,entity,state);
                name=(String)details.invoke(null,name,entity,translator);
                expect(name,"minecraft:"+COLORS[dye]+"_bed");
                expect(textures(bake("Bedrock_Beds.json",name,entity)),Set.of("minecraft:entity/bed/"+COLORS[dye]));
                // A separately named modern bed retains its explicit color.
                expect(details.invoke(null,"minecraft:red_bed",entity,translator),"minecraft:red_bed");
            }
            for(String source:new String[]{"undyed_shulker_box","blue_shulker_box","black_shulker_box","shulker_box"}) {
                NbtTagCompound state=props(),entity=props();
                state.addElement(NbtTagString.newNonPooledInstance("color","red"));
                String name=(String)palette.invoke(null,"minecraft:"+source,state,translator);
                entity.addElement(NbtTagByte.newNonPooledInstance("facing",(byte)1));
                merge.invoke(null,entity,state);
                String expected=source.equals("undyed_shulker_box")?"shulker":source.equals("shulker_box")?"shulker_red":"shulker_"+source.substring(0,source.indexOf("_shulker"));
                expect(textures(bake("Bedrock_Shulkers.json",name,entity)),Set.of("minecraft:entity/shulker/"+expected));
                expect(entity.get("facing").asInt(),1);
            }
            for(String attachment:new String[]{"standing","hanging","side","multiple"}) {
                NbtTagCompound state=props();state.addElement(NbtTagString.newNonPooledInstance("attachment",attachment));
                state.addElement(NbtTagInt.newNonPooledInstance("direction",2));
                expect(palette.invoke(null,"minecraft:bell",state,translator),"minecraft:bell");
                String expected=attachment.equals("standing")?"floor":attachment.equals("hanging")?"ceiling":attachment.equals("side")?"single_wall":"double_wall";
                expect(state.get("attachment").asString(),expected);
                NbtTagCompound entity=props();merge.invoke(null,entity,state);
                expect(details.invoke(null,"minecraft:bell",entity,translator),"minecraft:bell");
                expect(entity.get("attachment").asString(),expected);
                expect(entity.get("facing").asString(),"south");
            }
            for(String name:new String[]{"piston","sticky_piston"})for(int animation=0;animation<4;animation++) {
                NbtTagCompound state=props(),entity=props();
                state.addElement(NbtTagInt.newNonPooledInstance("facing_direction",1));
                palette.invoke(null,"minecraft:"+name,state,translator);
                entity.addElement(NbtTagByte.newNonPooledInstance("State",(byte)animation));merge.invoke(null,entity,state);
                details.invoke(null,"minecraft:"+name,entity,translator);
                expect(entity.get("extended").asString(),animation==1||animation==2?"true":"false");
            }
        } finally {
            packs.clear();packs.addAll(previous);
            try(var paths=Files.walk(root)){for(Path path:paths.sorted(Comparator.reverseOrder()).toList())Files.delete(path);}
        }
    }
    static void runChecks() throws Exception {
        String reference=System.getProperty("miex.copperGeometry");
        if(reference!=null) {
            JsonObject geo=JsonParser.parseString(Files.readString(Path.of(reference))).getAsJsonObject().getAsJsonArray("minecraft:geometry").get(0).getAsJsonObject();
            var handler=new nl.bramstout.mcworldexporter.resourcepack.bedrock.ModelHandlerBedrockEdition(null,geo);
            Model nativeModel=new Model("native reference",null,false,false);handler.getGeometry(nativeModel);nativeModel.applyBones();nativeModel.translate(8,0,8);
            expect(vertexUVs(bake("Bedrock_Copper_Statues.json","minecraft:copper_golem_statue",props())),vertexUVs(nativeModel));
        }
        expect(bake("Bedrock_End_Portals.json","minecraft:end_portal",props()).getFaces().size(),1);
        expect(bake("Bedrock_End_Portals.json","minecraft:end_gateway",props()).getFaces().size(),6);
        expect(textures(bake("Bedrock_End_Portals.json","minecraft:end_gateway",props())),Set.of("minecraft:block/end_portal"));
        checkPaletteAndEntityStates();
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
            // Legacy Bedrock bed stores color in the block entity.
            ExprContext ctx=evaluate("Bedrock_Beds.json","minecraft:bed",bed);
            expect(ctx.variables.get("color").asString(),COLORS[dye]);
            expect(ctx.variables.get("part").asString(),"head");
            // A named Bedrock color must not be replaced by a default/stale
            // metadata Color=0, which previously turned dyed beds white.
            ExprContext named=evaluate("Bedrock_Beds.json","minecraft:black_bed",bed);
            expect(named.variables.get("color").asString(),"black");
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
        // Older Bedrock worlds encode shulker dye in a 'color' block state,
        // whereas newer worlds have separate IDs for every dyed shulker box.
        for(String dye:COLORS) {
            NbtTagCompound legacy=props();
            legacy.addElement(NbtTagString.newNonPooledInstance("color",dye.equals("light_gray")?"silver":dye));
            ExprContext legacyCtx=evaluate("Bedrock_Shulkers.json","minecraft:shulker_box",legacy);
            expect(legacyCtx.variables.get("type").asString(),"shulker_"+dye);
            ExprContext explicitCtx=evaluate("Bedrock_Shulkers.json","minecraft:"+dye+"_shulker_box",legacy);
            expect(explicitCtx.variables.get("type").asString(),"shulker_"+dye);
        }
        NbtTagCompound conflicting=props();
        conflicting.addElement(NbtTagString.newNonPooledInstance("color","white"));
        expect(evaluate("Bedrock_Shulkers.json","minecraft:red_shulker_box",conflicting)
            .variables.get("type").asString(),"shulker_red");
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
        // The actual MiEx glyph advances (including formatting and bold
        // spacing), not character counts, limit the visible sign line width.
        Class<?> fontType=nl.bramstout.mcworldexporter.resourcepack.Font.class;
        Method fitLine=normalize.getDeclaringClass().getDeclaredMethod("fitBedrockSignLine",String.class,fontType,float.class);
        Method fitSide=normalize.getDeclaringClass().getDeclaredMethod("fitBedrockSignSide",NbtTagCompound.class,fontType,float.class);
        fitLine.setAccessible(true);
        fitSide.setAccessible(true);
        nl.bramstout.mcworldexporter.resourcepack.Font testFont =
            new nl.bramstout.mcworldexporter.resourcepack.Font() {
                @Override public Character getCharacterInfo(int codepoint) {
                    return new Character("minecraft:font/default",0.625f,1.0f,1.0f,0,0,1,1);
                }
            };
        expect(fitLine.invoke(null,"ABCDEFGHIJKLMNO",testFont,11.25f),"ABCDEFGHIJKLMNO");
        expect(fitLine.invoke(null,"ABCDEFGHIJKLMNOP",testFont,11.25f),"ABCDEFGHIJKLMNO");
        expect(fitLine.invoke(null,"ABCDEFGHIJK",testFont,7.5f),"ABCDEFGHIJ");
        expect(fitLine.invoke(null,"§aABCDEFGHIJKLMNO§r",testFont,11.25f),"§aABCDEFGHIJKLMNO§r");
        expect(fitLine.invoke(null,"§lABCDEFGHIJKLMN",testFont,11.25f),"§lABCDEFGHIJKLM");
        NbtTagCompound longText=props();
        longText.addElement(NbtTagString.newNonPooledInstance("Text",
            "ABCDEFGHIJKLMNOP\n12345678901234567"));
        fitSide.invoke(null,longText,testFont,11.25f);
        expect(longText.get("Text").asString(),"ABCDEFGHIJKLMNO\nP\n123456789012345\n67");
        NbtTagCompound cookingSign=props();
        cookingSign.addElement(NbtTagString.newNonPooledInstance("Text",
            "FREE COOKING SERVICES PROVIDED"));
        fitSide.invoke(null,cookingSign,testFont,11.25f);
        expect(cookingSign.get("Text").asString(),"FREE COOKING\nSERVICES\nPROVIDED");
        NbtTagCompound formattedSign=props();
        formattedSign.addElement(NbtTagString.newNonPooledInstance("Text",
            "§aFREE COOKING SERVICES PROVIDED"));
        fitSide.invoke(null,formattedSign,testFont,11.25f);
        expect(formattedSign.get("Text").asString(),"§aFREE COOKING\n§aSERVICES\n§aPROVIDED");
        NbtTagCompound hangingCookingSign=props();
        hangingCookingSign.addElement(NbtTagString.newNonPooledInstance("Text",
            "FREE COOKING SERVICES PROVIDED"));
        fitSide.invoke(null,hangingCookingSign,testFont,7.5f);
        expect(hangingCookingSign.get("Text").asString(),"FREE\nCOOKING\nSERVICES\nPROVIDED");
        NbtTagCompound fourLineSign=props();
        fourLineSign.addElement(NbtTagString.newNonPooledInstance("Text",
            "FREE COOKING SERVICES PROVIDED FOR EVERYONE"));
        fitSide.invoke(null,fourLineSign,testFont,11.25f);
        expect(fourLineSign.get("Text").asString(),"FREE COOKING\nSERVICES\nPROVIDED FOR\nEVERYONE");
        NbtTagCompound fiveLineOverflow=props();
        fiveLineOverflow.addElement(NbtTagString.newNonPooledInstance("Text",
            "FREE COOKING SERVICES PROVIDED FOR EVERYONE IN THE VILLAGE"));
        fitSide.invoke(null,fiveLineOverflow,testFont,11.25f);
        expect(fiveLineOverflow.get("Text").asString(),"FREE COOKING\nSERVICES\nPROVIDED FOR\nEVERYONE IN THE");
        NbtTagCompound unbrokenSign=props();
        unbrokenSign.addElement(NbtTagString.newNonPooledInstance("Text",
            "FREE_COOKING_SERVICES_PROVIDED"));
        fitSide.invoke(null,unbrokenSign,testFont,11.25f);
        expect(unbrokenSign.get("Text").asString(),"FREE_COOKING_SE\nRVICES_PROVIDED");
        NbtTagCompound longWordWrap=props();
        longWordWrap.addElement(NbtTagString.newNonPooledInstance("Text",
            "Notice: SUPERCALIFRAGILISTICEXPIALIDOCIOUS"));
        fitSide.invoke(null,longWordWrap,testFont,11.25f);
        expect(longWordWrap.get("Text").asString(),"Notice:\nSUPERCALIFRAGIL\nISTICEXPIALIDOC\nIOUS");
        NbtTagCompound crlfSign=props();
        crlfSign.addElement(NbtTagString.newNonPooledInstance("Text",
            "Line 1\r\nLine 2\r\nLine 3"));
        fitSide.invoke(null,crlfSign,testFont,11.25f);
        expect(crlfSign.get("Text").asString(),"Line 1\nLine 2\nLine 3");
        NbtTagCompound indentSign=props();
        indentSign.addElement(NbtTagString.newNonPooledInstance("Text",
            "  Indented"));
        fitSide.invoke(null,indentSign,testFont,11.25f);
        expect(indentSign.get("Text").asString(),"  Indented");
        NbtTagCompound fullSignNormal=props();
        fullSignNormal.addElement(NbtTagString.newNonPooledInstance("Text",
            "FREE COOKING SERVICES PROVIDED"));
        normalizeSign.invoke(null,"minecraft:oak_sign",fullSignNormal);
        expect(((NbtTagCompound)fullSignNormal.get("FrontText")).get("Text").asString(),"FREE COOKING\nSERVICES\nPROVIDED");
        expect(fullSignNormal.get("Text").asString(),"FREE COOKING\nSERVICES\nPROVIDED");
        NbtTagCompound fullHangingNormal=props();
        fullHangingNormal.addElement(NbtTagString.newNonPooledInstance("Text",
            "FREE COOKING SERVICES PROVIDED"));
        normalizeSign.invoke(null,"minecraft:oak_hanging_sign",fullHangingNormal);
        expect(((NbtTagCompound)fullHangingNormal.get("FrontText")).get("Text").asString(),"FREE\nCOOKING\nSERVICES\nPROVIDED");
        NbtTagCompound fullUnbrokenNormal=props();
        fullUnbrokenNormal.addElement(NbtTagString.newNonPooledInstance("Text",
            "FREE_COOKING_SERVICES_PROVIDED"));
        normalizeSign.invoke(null,"minecraft:oak_sign",fullUnbrokenNormal);
        expect(((NbtTagCompound)fullUnbrokenNormal.get("FrontText")).get("Text").asString(),"FREE_COOKING_SE\nRVICES_PROVIDED");
        ExprContext ctx=evaluate("Bedrock_Beds.json","minecraft:bed",frame);
        expect(ExprParser.parseMultiExpression("thisEntity.state.x != null ? (0.5 + thisEntity.state.x) : 0.0").eval(ctx).asFloat(),-6.5f);
        expect(ExprParser.parseMultiExpression("thisEntity.state.z != null ? (0.5 + thisEntity.state.z) : 0.0").eval(ctx).asFloat(),0f);
        System.out.println("Pinned MiEx runtime: chest halves/materials, copper statue geometry, chain resource compatibility, dyes, attachments and prior model regressions passed.");
        // ChunkBedrock starts MiEx's periodic background cache cleanup thread.
        System.exit(0);
    }
    static List<String> vertexUVs(Model model) {
        List<String> result=new ArrayList<>();float[] points=new float[12],uvs=new float[8];
        for(var face:model.getFaces()) {face.getPoints(points);face.getUVs(uvs);
            for(int i=0;i<4;i++)result.add(Math.round(points[i*3]*10000)+","+Math.round(points[i*3+1]*10000)+","+Math.round(points[i*3+2]*10000)+","+Math.round(uvs[i*2]*10000)+","+Math.round(uvs[i*2+1]*10000));
        }
        Collections.sort(result);return result;
    }
    public static void main(String[] args) {
        try { runChecks(); }
        catch(Throwable ex) { ex.printStackTrace(); System.exit(1); }
    }
}
