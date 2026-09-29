import { useState } from "react";
import { Text } from "react-native";
import { Redirect, router, useLocalSearchParams } from "expo-router";
import { useSession } from "../core/runtime";
import { Button, ErrorPanel, Screen, styles } from "../ui/common";
export default function Recovery() {
  const session = useSession();
  const { form } = useLocalSearchParams<{ form: string }>();
  const [busy, setBusy] = useState(false);
  const [openedAt] = useState(Date.now);
  if (!session.account || typeof form !== "string")
    return <Redirect href="/" />;
  const scope = session.scope();
  const intent = session
    .unresolved()
    .find((x) => x.form === form && x.garden === scope.garden);
  const outcome = session.outcome(scope, form);
  async function check(retry = false) {
    if (!intent) return;
    setBusy(true);
    try {
      if (retry)
        await session.submit(
          scope,
          form!,
          intent.request.path,
          intent.request.body!,
        );
      else await session.reconcile(scope, form!);
    } catch {
      /* session owns the visible outcome */
    } finally {
      setBusy(false);
    }
  }
  return (
    <Screen title="Kontrollera sparningen" back={() => router.replace("/")}>
      {outcome?.result ? (
        <Text style={styles.text}>
          Servern har bekräftat sparningen. Historiken hämtas från servern när
          du öppnar trädgården.
        </Text>
      ) : null}
      <ErrorPanel error={outcome?.error} />
      {intent && (
        <>
          <Text style={styles.text}>
            Kontrollera först om servern redan har sparat. Begäran finns kvar på
            denna enhet tills svaret är säkert.
          </Text>
          <Text selectable style={styles.muted}>
            Begäransnyckel: {intent.request.key}
          </Text>
          <Text selectable style={styles.muted}>
            {form === "workspace"
              ? (() => {try{return JSON.parse(session.draft(scope,form).editor).title;}catch{return "Din ändring i trädgården";}})()
              : JSON.stringify(intent.request.body)}
          </Text>
          <Button
            title="Hämta sparat kvitto"
            disabled={busy}
            onPress={() => check()}
          />
          {openedAt - intent.started < 7 * 86400000 ? (
            <Button
              title="Försök spara samma begäran igen"
              disabled={busy}
              secondary
              onPress={() => check(true)}
            />
          ) : (
            <Text style={styles.text}>
              Mer än sju dagar har gått. Inget nytt sparförsök görs. Om kvitto
              saknas behöver administratören kontrollera historik och databas
              med begäransnyckeln ovan.
            </Text>
          )}
        </>
      )}
      <Button
        title="Till trädgårdarna"
        secondary
        onPress={() => {
          session.selectGarden(null);
          router.replace("/");
        }}
      />
    </Screen>
  );
}
