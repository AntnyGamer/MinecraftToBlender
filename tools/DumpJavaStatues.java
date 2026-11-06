import java.lang.reflect.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import com.google.gson.*;
import net.minecraft.client.model.geom.ModelPart;
import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.core.Direction;
import org.joml.Quaternionf;
import org.joml.Vector3f;
/** Developer-only reference extractor. Requires the official Java 26.1.2
 * client and its normal dependencies on a Java 25 classpath. Writes numeric
 * geometry/UV facts only; neither client code nor images are distributed.
 */
public class DumpJavaStatues {
    static Object field(Object value,String name)throws Exception {
        Field f=value.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(value);
    }
    static Object number(Object value,String method)throws Exception {
        return value.getClass().getMethod(method).invoke(value);
    }
    static JsonArray vector(Object value)throws Exception {
        JsonArray a=new JsonArray();for(String axis:List.of("x","y","z"))a.add((Number)number(value,axis));return a;
    }
    static JsonObject part(Object value)throws Exception {
        JsonObject out=new JsonObject(),pose=new JsonObject();Object p=field(value,"partPose");
        for(String name:List.of("x","y","z","xRot","yRot","zRot","xScale","yScale","zScale"))pose.addProperty(name,(Number)number(p,name));
        out.add("pose",pose);JsonArray cubes=new JsonArray();
        for(Object c:(List<?>)field(value,"cubes")) {
            JsonObject cube=new JsonObject();cube.add("origin",vector(field(c,"origin")));cube.add("size",vector(field(c,"dimensions")));
            JsonArray uv=new JsonArray();Object t=field(c,"texCoord");uv.add((Number)number(t,"u"));uv.add((Number)number(t,"v"));cube.add("uv",uv);
            Object grow=field(c,"grow");JsonArray inflation=new JsonArray();for(String axis:List.of("growX","growY","growZ"))inflation.add((Number)field(grow,axis));cube.add("inflate",inflation);
            cube.addProperty("mirror",(Boolean)field(c,"mirror"));JsonArray faces=new JsonArray();for(Object face:(Set<?>)field(c,"visibleFaces"))faces.add(face.toString());cube.add("faces",faces);cubes.add(cube);
        }
        out.add("cubes",cubes);JsonObject children=new JsonObject();
        for(var child:((Map<String,?>)field(value,"children")).entrySet())children.add(child.getKey(),part(child.getValue()));
        out.add("children",children);return out;
    }
    public static void main(String[] args)throws Exception {
        if(args.length != 1)throw new IllegalArgumentException("Expected output JSON path");
        Path client=Path.of(ModelPart.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        MessageDigest hash=MessageDigest.getInstance("SHA-1");
        try(var input=Files.newInputStream(client)) {
            byte[] buffer=new byte[65536];int count;
            while((count=input.read(buffer))>=0)hash.update(buffer,0,count);
        }
        if(!HexFormat.of().formatHex(hash.digest()).equals("4e618f09a0c649dde3fdf829df443ce0b8831e65"))
            throw new IllegalStateException("Reference client SHA-1 mismatch");
        Class<?> model=Class.forName("net.minecraft.client.model.animal.golem.CopperGolemModel");JsonObject out=new JsonObject();
        for(var item:Map.of("standing","createBodyLayer","sitting","createSittingPoseBodyLayer","running","createRunningPoseBodyLayer","star","createStarPoseBodyLayer").entrySet()) {
            Object layer=model.getMethod(item.getValue()).invoke(null),mesh=field(layer,"mesh"),material=field(layer,"material");
            JsonObject data=new JsonObject();data.addProperty("width",(Number)field(material,"xTexSize"));data.addProperty("height",(Number)field(material,"yTexSize"));data.add("root",part(mesh.getClass().getMethod("getRoot").invoke(mesh)));
            ModelPart baked=(ModelPart)layer.getClass().getMethod("bakeRoot").invoke(layer);baked.y=0;baked.zRot=(float)Math.PI;
            JsonObject directions=new JsonObject();
            for(Direction direction:List.of(Direction.NORTH,Direction.EAST,Direction.SOUTH,Direction.WEST)) {
                PoseStack stack=new PoseStack();stack.translate(.5,0,.5);stack.mulPose(new Quaternionf().rotationY((float)Math.toRadians(-direction.getOpposite().toYRot())));
                JsonArray faces=new JsonArray();
                baked.visit(stack,(pose,path,index,cube)->{
                    for(var polygon:cube.polygons) {
                        JsonArray vertices=new JsonArray();
                        for(var v:polygon.vertices()) {
                            Vector3f xyz=pose.pose().transformPosition(new Vector3f(v.worldX(),v.worldY(),v.worldZ()));
                            JsonArray vertex=new JsonArray();vertex.add(xyz.x*16);vertex.add(xyz.y*16);vertex.add(xyz.z*16);vertex.add(v.u()*16);vertex.add(16-v.v()*16);vertices.add(vertex);
                        }
                        faces.add(vertices);
                    }
                });directions.add(direction.getSerializedName(),faces);
            }
            data.add("directions",directions);out.add(item.getKey(),data);
        }
        Files.writeString(Path.of(args[0]),new GsonBuilder().setPrettyPrinting().create().toJson(out));System.out.println("NATIVE_JAVA_POSES_EXTRACTED "+out.keySet());
    }
}
