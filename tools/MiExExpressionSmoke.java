import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import nl.bramstout.mcworldexporter.expression.ExprParser;

public final class MiExExpressionSmoke {
    public static void main(String[] args) throws Exception {
        BufferedReader input = new BufferedReader(
            new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line;
        int checked = 0;
        while ((line = input.readLine()) != null) {
            if (line.isBlank()) {
                continue;
            }
            try {
                ExprParser.parseMultiExpression(line);
            } catch (RuntimeException problem) {
                throw new IllegalStateException(
                    "Pinned MiEx rejected resource-pack expression: " + line, problem);
            }
            checked++;
        }
        if (checked < 10) {
            throw new IllegalStateException("Expected multiple Bedrock model expressions, got " + checked);
        }
        System.out.println("Pinned MiEx parsed " + checked + " Bedrock model expressions.");
    }
}
