import React, { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useFocusEffect, router } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { ApiError, Page, StaleContext } from "../api/contract";
import { useSession } from "../core/runtime";
export const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#f6f5ef" },
  page: {
    padding: 22,
    gap: 18,
    width: "100%",
    maxWidth: 660,
    alignSelf: "center",
    paddingBottom: 48,
  },
  eyebrow: {
    color: "#516348",
    fontSize: 13,
    letterSpacing: 2,
    fontWeight: "700",
  },
  title: { color: "#233b2b", fontSize: 32, fontWeight: "700", lineHeight: 39 },
  text: { color: "#384b3d", fontSize: 17, lineHeight: 25 },
  muted: { color: "#5d685e", fontSize: 14, lineHeight: 21 },
  card: {
    backgroundColor: "#fffefa",
    borderWidth: 1,
    borderColor: "#d9dfd2",
    borderRadius: 18,
    padding: 18,
    gap: 10,
  },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  button: {
    backgroundColor: "#294d36",
    minHeight: 50,
    borderRadius: 12,
    paddingHorizontal: 18,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  secondary: { backgroundColor: "#e7ebdf" },
  buttonText: { color: "#ffffff", fontSize: 16, fontWeight: "600" },
  secondaryText: { color: "#294d36" },
  input: {
    backgroundColor: "#fffefa",
    color: "#233b2b",
    borderWidth: 1,
    borderColor: "#91a08b",
    borderRadius: 10,
    padding: 14,
    fontSize: 17,
    minHeight: 52,
  },
  error: { backgroundColor: "#fff0e9", padding: 16, borderRadius: 12, gap: 10 },
  label: { color: "#233b2b", fontSize: 16, fontWeight: "600" },
});
export function Button({
  title,
  onPress,
  secondary = false,
  disabled = false,
}: {
  title: string;
  onPress: () => void;
  secondary?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.button,
        secondary && styles.secondary,
        disabled && { opacity: 0.5 },
      ]}
    >
      <Text style={[styles.buttonText, secondary && styles.secondaryText]}>
        {title}
      </Text>
    </Pressable>
  );
}
export function Screen({
  title,
  children,
  back,
}: React.PropsWithChildren<{ title: string; back?: () => void }>) {
  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.page}
        >
          <Text style={styles.eyebrow}>TRÄDGÅRDSRYTMEN</Text>
          <Text style={styles.muted}>
            Lokal förhandsvisning · endast exempeldata
          </Text>
          {back && <Button title="Tillbaka" secondary onPress={back} />}
          <Text accessibilityRole="header" style={styles.title}>
            {title}
          </Text>
          {children}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
export function Field({
  label,
  value,
  onChange,
  multiline = false,
  disabled = false,
  error,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  multiline?: boolean;
  disabled?: boolean;
  error?: string;
}) {
  return (
    <View style={{ gap: 7 }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        editable={!disabled}
        onChangeText={onChange}
        multiline={multiline}
        style={[
          styles.input,
          multiline && { minHeight: 108, textAlignVertical: "top" },
        ]}
      />
      {error && (
        <Text accessibilityRole="alert" style={styles.text}>
          {error}
        </Text>
      )}
    </View>
  );
}
export function ErrorPanel({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  if (!error || error instanceof StaleContext) return null;
  return (
    <View accessibilityRole="alert" style={styles.error}>
      <Text style={styles.text}>
        {error instanceof Error ? error.message : "Något gick fel."}
      </Text>
      {retry && <Button title="Försök igen" onPress={retry} secondary />}
    </View>
  );
}
export function Loading() {
  return (
    <View style={styles.row}>
      <ActivityIndicator color="#294d36" />
      <Text style={styles.text}>Hämtar…</Text>
    </View>
  );
}
export function fieldError(error: unknown, field: string) {
  if (!(error instanceof ApiError)) return undefined;
  const code = error.body.error.fields[field]?.[0];
  return code
    ? ({
        required: "Fyll i fältet.",
        invalid: "Kontrollera värdet.",
        too_long: "Texten är för lång.",
        unknown: "Fältet stöds inte.",
      }[code] ?? "Kontrollera fältet.")
    : undefined;
}
/** A focused route owns its request result; blur and context generation both invalidate late responses. */
export function useResource<T>(path: string | null) {
  const session = useSession();
  const [state, set] = useState<{
    epoch: number;
    path: string | null;
    data?: T;
    error?: unknown;
    loading: boolean;
  }>({ epoch: session.epoch, path, loading: true });
  const [revision, refresh] = useState(0);
  const request = useRef(0);
  const epoch = session.epoch;
  useFocusEffect(
    useCallback(() => {
      void revision;
      void epoch;
      const id = ++request.current;
      if (!path || !session.account) return;
      const scope = session.scope();
      set({ epoch: scope.epoch, path, loading: true });
      session
        .read<T>(scope, path)
        .then((data) => {
          if (id === request.current && session.current(scope))
            set({ epoch: scope.epoch, path, loading: false, data });
        })
        .catch((error) => {
          if (id === request.current && session.current(scope))
            set({ epoch: scope.epoch, path, loading: false, error });
        });
      return () => {
        request.current++;
      };
    }, [path, session, epoch, revision]),
  );
  const visible =
    state.epoch === session.epoch && state.path === path
      ? state
      : { loading: true, data: undefined, error: undefined };
  const reload = useCallback(() => refresh((v) => v + 1), []);
  return { ...visible, reload };
}
export function PagedList<T extends { id: string }>({
  path,
  empty,
  render,
}: {
  path: string;
  empty: string;
  render: (row: T) => React.ReactNode;
}) {
  const session = useSession();
  const base = path + (path.includes("?") ? "&" : "?") + "limit=2";
  const page = useResource<Page<T>>(base);
  const [extra, setExtra] = useState<{
    source?: Page<T>;
    rows: T[];
    cursor: string | null;
    error?: unknown;
    loading: boolean;
  }>({ rows: [], cursor: null, loading: false });
  const pending = useRef(false);
  const generation = useRef(0);
  useFocusEffect(
    useCallback(() => {
      generation.current++;
      pending.current = false;
      return () => {
        generation.current++;
        pending.current = false;
      };
    }, []),
  );
  const valid = page.data && extra.source === page.data;
  const rows = [...(page.data?.results ?? []), ...(valid ? extra.rows : [])];
  const cursor = valid ? extra.cursor : page.data?.next_cursor;
  async function more() {
    if (!cursor || pending.current || !page.data) return;
    const scope = session.scope(),
      source = page.data,
      gen = generation.current;
    const oldRows = valid ? extra.rows : [];
    pending.current = true;
    setExtra({ source, rows: oldRows, cursor, loading: true });
    try {
      const next = await session.read<Page<T>>(
        scope,
        base + "&cursor=" + encodeURIComponent(cursor),
      );
      if (session.current(scope) && gen === generation.current)
        setExtra({
          source,
          rows: [...oldRows, ...next.results].filter(
            (r, i, a) => a.findIndex((x) => x.id === r.id) === i,
          ),
          cursor: next.next_cursor,
          loading: false,
        });
    } catch (error) {
      if (session.current(scope) && gen === generation.current)
        setExtra({ source, rows: oldRows, cursor, error, loading: false });
    } finally {
      if (gen === generation.current) pending.current = false;
    }
  }
  return (
    <View style={{ gap: 12 }}>
      {page.loading && <Loading />}
      <ErrorPanel error={page.error} retry={page.reload} />
      {page.data && !rows.length && (
        <View style={styles.card}>
          <Text style={styles.text}>{empty}</Text>
        </View>
      )}
      {rows.map((row) => (
        <React.Fragment key={row.id}>{render(row)}</React.Fragment>
      ))}
      {valid && <ErrorPanel error={extra.error} retry={more} />}
      {cursor && (
        <Button
          title={valid && extra.loading ? "Hämtar fler…" : "Visa fler"}
          secondary
          disabled={valid && extra.loading}
          onPress={more}
        />
      )}
    </View>
  );
}
export function backToGarden() {
  router.replace("/garden");
}

/** Prevent an old form from navigating after it loses focus while saving. */
export function useRouteFocus() {
  const focused = useRef(false);
  useFocusEffect(
    useCallback(() => {
      focused.current = true;
      return () => {
        focused.current = false;
      };
    }, []),
  );
  return focused;
}
