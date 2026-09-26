import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useSession } from "../core/runtime";
export default function Layout() {
  const session = useSession();
  return (
    <>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false, animation: "none" }}>
        <Stack.Screen name="index" />
        <Stack.Protected guard={!!session.account}>
          <Stack.Screen name="new" />
        </Stack.Protected>
        <Stack.Protected guard={!!session.account && !!session.garden}>
          <Stack.Screen name="garden" />
          <Stack.Screen name="plant" />
          <Stack.Screen name="task" />
        </Stack.Protected>
      </Stack>
    </>
  );
}
