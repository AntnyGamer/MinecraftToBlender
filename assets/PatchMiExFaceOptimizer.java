import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.jar.*;

/**
 * Portable, fail-closed patch for MiEx experimental-34's incorrect final
 * vertex-color lookup. Uses only public Java APIs, no internal ASM or modules.
 * Verifies the exact official JAR first, modifies one byte in one class,
 * then verifies the resulting method and leaves the original intact.
 */
public final class PatchMiExFaceOptimizer {
    private static final String TARGET =
        "nl/bramstout/mcworldexporter/export/processors/FaceOptimiser$CombinedFace.class";
    private static final String EXPECTED =
        "e4951d44116fd2d90c14f52643b7cd66ddd7f64ac108b8a16705b379672de707";

    // ClassFile reading is deliberately read-only, except the verified opcode.
    private static final class ClassView {
        final ByteBuffer b;
        final String[] utf8;
        final int[] tag;
        final int[] left;
        final int[] right;
        final int codeStart;
        final int codeLength;
        ClassView(byte[] bytes) {
            b = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN);
            if (b.getInt() != 0xCAFEBABE) throw new IllegalStateException("Not a Java class");
            b.getShort(); b.getShort();
            int count = u2();
            utf8 = new String[count]; tag = new int[count]; left = new int[count]; right = new int[count];
            for (int i = 1; i < count; i++) {
                int t = u1(); tag[i] = t;
                switch (t) {
                    case 1 -> { int n = u2(); byte[] data = new byte[n]; b.get(data); utf8[i] = new String(data, StandardCharsets.UTF_8); }
                    case 3, 4 -> skip(4);
                    case 5, 6 -> {skip(8); i++;}
                    case 7, 8, 16, 19, 20 -> left[i] = u2();
                    case 9, 10, 11, 12, 17, 18 -> {left[i] = u2(); right[i] = u2();}
                    case 15 -> {left[i] = u1(); right[i] = u2();}
                    default -> throw new IllegalStateException("Unexpected constant-pool tag " + t);
                }
            }
            b.getShort(); // access flags
            int thisClass = u2(); b.getShort(); // this and super
            if (tag[thisClass] != 7 || !TARGET.substring(0, TARGET.length()-6).equals(utf8[left[thisClass]]))
                throw new IllegalStateException("Not the expected MiEx optimizer class");
            for (int i = u2(); i > 0; i--) b.getShort(); // interfaces
            for (int i = u2(); i > 0; i--) skipMember(); // fields
            int foundStart = -1, foundLength = -1, matches = 0;
            int methods = u2();
            for (int i = 0; i < methods; i++) {
                b.getShort(); int name = u2(), desc = u2(), attrs = u2();
                boolean setup = "setup".equals(utf8[name]) && utf8[desc] != null &&
                                utf8[desc].contains("/Mesh;I") && utf8[desc].endsWith(")V");
                if (setup) matches++;
                for (int j = 0; j < attrs; j++) {
                    int aname = u2(); long size = Integer.toUnsignedLong(b.getInt());
                    int end = checkedEnd(size);
                    if (setup && "Code".equals(utf8[aname])) {
                        b.getShort(); b.getShort();
                        int len = b.getInt();
                        if (len < 0 || len > end - b.position()) throw new IllegalStateException("Bad method code length");
                        foundStart = b.position(); foundLength = len;
                    }
                    b.position(end);
                }
            }
            if (matches != 1 || foundStart < 0) throw new IllegalStateException("Expected one CombinedFace.setup(Mesh,int)");
            codeStart = foundStart; codeLength = foundLength;
        }
        int u1() {return Byte.toUnsignedInt(b.get());}
        int u2() {return Short.toUnsignedInt(b.getShort());}
        void skip(int n) {b.position(b.position()+n);}
        int checkedEnd(long n) {
            if (n < 0 || n > b.remaining()) throw new IllegalStateException("Invalid class-file attribute length");
            return b.position() + (int)n;
        }
        void skipMember() {
            b.getShort(); b.getShort(); b.getShort();
            for (int n = u2(); n > 0; n--) {b.getShort(); b.position(checkedEnd(Integer.toUnsignedLong(b.getInt())));}
        }
        boolean method(int index, String name, String desc) {
            if (index < 1 || index >= tag.length || (tag[index] != 10 && tag[index] != 11)) return false;
            int nat = right[index];
            return tag[nat] == 12 && name.equals(utf8[left[nat]]) && desc.equals(utf8[right[nat]]);
        }
        boolean callAtMethodNamed(int pos, String name) {
            if (pos < codeStart || pos + 3 > codeStart+codeLength || Byte.toUnsignedInt(b.get(pos)) != 0xb6) return false;
            int index = Short.toUnsignedInt(b.getShort(pos+1));
            if (index < 1 || index >= tag.length || (tag[index] != 10 && tag[index] != 11)) return false;
            int nat = right[index];
            return tag[nat] == 12 && name.equals(utf8[left[nat]]);
        }
        boolean callAt(int pos, String name, String desc) {
            if (pos < codeStart || pos + 3 > codeStart+codeLength || Byte.toUnsignedInt(b.get(pos)) != 0xb6) return false;
            return method(Short.toUnsignedInt(b.getShort(pos + 1)), name, desc);
        }
    }

    private static byte[] patch(byte[] original) {
        byte[] patched = original.clone();
        ClassView cls = new ClassView(patched);
        List<Integer> offsets = new ArrayList<>();
        List<Integer> corners = new ArrayList<>();
        int end = cls.codeStart + cls.codeLength;
        // Match the exact javac-generated instruction sequence for this MiEx
        // release, and require four direct calls to colors.getIndex(I)I.
        for (int j = cls.codeStart + 6; j + 2 < end; j++) {
            if (!cls.callAt(j, "getIndex", "(I)I")) continue;
            int offset = -1, corner = -1;
            if (j >= cls.codeStart+3 &&
                unsigned(patched[j-3]) == 0x1c && unsigned(patched[j-2]) == 0x07 &&
                unsigned(patched[j-1]) == 0x68) {
                // first corner: index = face * 4
                offset = -1; corner = 0;
            } else if (j >= cls.codeStart+5 &&
                unsigned(patched[j-5]) == 0x1c && unsigned(patched[j-4]) == 0x07 &&
                unsigned(patched[j-3]) == 0x68 && unsigned(patched[j-1]) == 0x60 &&
                unsigned(patched[j-2]) >= 0x04 && unsigned(patched[j-2]) <= 0x07) {
                offset = j-2; corner = unsigned(patched[offset]) - 0x03;
            } else continue;
            // Require this exact method call to read the mesh's color channel.
            // First reads have 6 bytes between getColors and getIndex;
            // remaining reads have 8 bytes. This excludes AO and UV lookups.
            int getter = j - (corner == 0 ? 6 : 8);
            if (!cls.callAt(getter, "getColors", "()Lnl/bramstout/mcworldexporter/model/VertexColors;")) {
                // Return type can vary between MiEx revisions; the SHA-256
                // lock prevents applying this to unfamiliar versions.
                if (!cls.callAtMethodNamed(getter, "getColors")) continue;
            }
            corners.add(corner); offsets.add(offset);
        }
        if (!corners.equals(Arrays.asList(0,1,2,2)))
            throw new IllegalStateException("Unsupported optimizer bytecode: found color corners " + corners);
        if (offsets.get(3) < 0 || unsigned(patched[offsets.get(3)]) != 0x05)
            throw new IllegalStateException("Fourth-corner opcode is not iconst_2");
        patched[offsets.get(3)] = 0x06; // iconst_3, same size, stack and control flow
        ClassView after = new ClassView(patched);
        if (after.codeStart != cls.codeStart || after.codeLength != cls.codeLength)
            throw new IllegalStateException("Method changed unexpectedly");
        int changes=0; for(int i=0;i<original.length;i++) if(original[i]!=patched[i]) changes++;
        if (changes != 1) throw new IllegalStateException("Patch must change precisely one byte");
        return patched;
    }

    private static int unsigned(byte b) {return Byte.toUnsignedInt(b);}
    private static String sha256(Path path) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        try (InputStream in = Files.newInputStream(path)) {
            byte[] buffer=new byte[65536]; int n;
            while ((n=in.read(buffer))>=0) md.update(buffer,0,n);
        }
        return HexFormat.of().formatHex(md.digest());
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("Usage: PatchMiExFaceOptimizer INPUT.jar OUTPUT.jar");
        Path input=Path.of(args[0]), output=Path.of(args[1]);
        if (Files.exists(output) && Files.isSameFile(input,output))
            throw new IllegalArgumentException("Input and output must be separate JARs");
        if (!EXPECTED.equalsIgnoreCase(sha256(input)))
            throw new SecurityException("Official MiEx checksum mismatch; refusing unfamiliar JAR");
        Path temp=output.resolveSibling(output.getFileName()+".partial");
        try {
            int modified=0;
            try (JarFile source=new JarFile(input.toFile());
                 JarOutputStream dest=new JarOutputStream(Files.newOutputStream(temp))) {
                Enumeration<JarEntry> entries=source.entries();
                while (entries.hasMoreElements()) {
                    JarEntry entry=entries.nextElement();
                    String name=entry.getName();
                    if (name.startsWith("META-INF/") &&
                        (name.endsWith(".SF") || name.endsWith(".RSA") || name.endsWith(".DSA")))
                        throw new SecurityException("Signed JAR; refusing to rewrite");
                    JarEntry copy=new JarEntry(name);
                    copy.setTime(entry.getTime());
                    dest.putNextEntry(copy);
                    try (InputStream in=source.getInputStream(entry)) {
                        if (name.equals(TARGET)) {
                            if (++modified != 1) throw new IllegalStateException("Duplicate target class");
                            dest.write(patch(in.readAllBytes()));
                        } else {
                            // Stream unmodified entries rather than loading entire
                            // decompressed JAR entries into memory.
                            in.transferTo(dest);
                        }
                    }
                    dest.closeEntry();
                }
            }
            if (modified != 1) throw new IllegalStateException("Target face optimizer class missing");
            try (JarFile check=new JarFile(temp.toFile())) {
                byte[] patched;
                try (InputStream in=check.getInputStream(check.getJarEntry(TARGET))) {patched=in.readAllBytes();}
                // Constructor and class structure must be readable after patch.
                new ClassView(patched);
            }
            Files.move(temp,output,StandardCopyOption.REPLACE_EXISTING);
            System.out.println("PASS: portable MiEx face patch applied; changed exactly one byte in CombinedFace.setup.");
            System.out.println("Original verified and unchanged; optimized JAR SHA256: " + sha256(output));
        } catch(Exception ex) {
            Files.deleteIfExists(temp);
            throw ex;
        }
    }
}
