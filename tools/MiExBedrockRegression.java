import java.nio.file.*;
import java.lang.reflect.Method;
import java.util.*;
import com.google.gson.*;
import nl.bramstout.mcworldexporter.expression.*;
import nl.bramstout.mcworldexporter.expression.ExprValue.ExprValueDict;
import nl.bramstout.mcworldexporter.nbt.*;

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
    public static void main(String[] args) throws Exception {
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
        System.out.println("Pinned MiEx runtime: bed/banner dyes, ominous layers, shulkers, frames, standing/wall/hanging sign rotations and both text sides passed.");
        // ChunkBedrock starts MiEx's periodic background cache cleanup thread.
        System.exit(0);
    }
}
