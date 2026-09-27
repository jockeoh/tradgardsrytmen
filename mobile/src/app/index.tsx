import { useEffect, useState } from "react";
import { Text, View } from "react-native";
import { router } from "expo-router";
import { Garden } from "../api/contract";
import { accounts } from "../api/fixtures";
import { demo, server, useSession } from "../core/runtime";
import {
  Button,
  ErrorPanel,
  Field,
  PagedList,
  Screen,
  styles,
} from "../ui/common";
export default function Home() {
  const session = useSession();
  const [tools, setTools] = useState(false);
  const [origin, setOrigin] = useState(
    process.env.EXPO_PUBLIC_API_ORIGIN ?? "",
  );
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(!demo);
  const [error, setError] = useState<unknown>();
  async function resume() {
    setBusy(true);
    setError(undefined);
    try {
      await (await import("../core/device-connection")).reconnect(session);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (demo) return;
    let active = true;
    import("../core/device-connection")
      .then(async (connection) => {
        if (!session.account) await connection.reconnect(session);
      })
      .catch((e) => {
        if (active) setError(e);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [session]);
  async function login() {
    setBusy(true);
    setError(undefined);
    try {
      await (
        await import("../core/device-connection")
      ).connect(session, origin, username, password);
      setPassword("");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    if (demo) {
      session.logout();
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      await (await import("../core/device-connection")).disconnect(session);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Screen title={session.account ? "Dina trädgårdar" : "En sak i taget."}>
      {session.notice ? (
        <Text accessibilityRole="alert" style={styles.text}>
          {session.notice}
        </Text>
      ) : null}
      <ErrorPanel error={error} retry={resume} />
      {!session.account && !demo ? (
        <>
          <Text style={styles.text}>
            Logga in med ditt privata trädgårdskonto.
          </Text>
          <Field
            label="Serveradress"
            value={origin}
            onChange={setOrigin}
            disabled={busy}
          />
          <Field
            label="Användarnamn"
            value={username}
            onChange={setUsername}
            disabled={busy}
          />
          <Field
            label="Lösenord"
            value={password}
            onChange={setPassword}
            secureTextEntry
            disabled={busy}
          />
          <Button
            title={busy ? "Ansluter…" : "Logga in"}
            onPress={login}
            disabled={busy || !origin || !username || !password}
          />
          <Text style={styles.muted}>
            Saknar du lösenord? Be den som sköter servern om en privat
            lösenordslänk.
          </Text>
        </>
      ) : !session.account ? (
        <>
          <Text style={styles.text}>
            Välj ett provkonto och ta hand om din trädgård. Allt du gör stannar
            i den här förhandsvisningen.
          </Text>
          {accounts.map((account) => (
            <Button
              key={account.id}
              title={account.display_name}
              onPress={() => {
                server.expired.delete(account.id);
                session.login(account, server.bind(account.id));
              }}
            />
          ))}
          <Text style={styles.muted}>
            Exempeldata återställs när appen startas om. Inga riktiga konton
            ansluts.
          </Text>
        </>
      ) : (
        <>
          <Text style={styles.text}>{session.account.display_name}</Text>
          {session.unresolved().map((item) => (
            <View style={styles.card} key={item.key}>
              <Text style={styles.label}>En sparning behöver bekräftas</Text>
              <Text style={styles.text}>
                {String(
                  item.request.body?.name ??
                    item.request.body?.title ??
                    "Klarmarkering",
                )}
              </Text>
              <Button
                title="Kontrollera sparningen"
                onPress={() => {
                  session.selectGarden(item.garden);
                  router.push({
                    pathname: "/recovery",
                    params: { form: item.form },
                  });
                }}
              />
            </View>
          ))}
          <PagedList<Garden>
            key={session.epoch}
            path="/api/v1/gardens/"
            empty="Ingen trädgård ännu. Skapa din första nedan."
            render={(garden) => (
              <View style={styles.card}>
                <Text style={styles.title}>{garden.name}</Text>
                <Text style={styles.muted}>
                  {garden.role === "owner" ? "Ägare" : "Medlem"}
                </Text>
                <Button
                  title={`Öppna ${garden.name}`}
                  onPress={() => {
                    session.selectGarden(garden.id);
                    router.push("/garden");
                  }}
                />
              </View>
            )}
          />
          <Button
            title="Skapa trädgård"
            secondary
            onPress={() => {
              session.selectGarden(null);
              router.push({ pathname: "/new", params: { kind: "garden" } });
            }}
          />
          <Button
            title="Byt konto / logga ut"
            secondary
            onPress={logout}
            disabled={busy}
          />
        </>
      )}
      {demo && (
        <Button
          title={tools ? "Dölj provverktyg" : "Visa provverktyg"}
          secondary
          onPress={() => setTools(!tools)}
        />
      )}
      {demo && tools && (
        <View style={styles.card}>
          <Text style={styles.text}>Simulera nästa anrop</Text>
          <Text style={styles.muted}>
            Endast lokal transport. Ett val påverkar nästa anrop; läsning kan
            förbruka felet innan du sparar.
          </Text>
          <Button
            title="Nätverksfel"
            secondary
            onPress={() => server.faults.push("network")}
          />
          <Button
            title="Förlorad session"
            secondary
            onPress={() => server.faults.push("401")}
          />
          <Button
            title="Saknad behörighet"
            secondary
            onPress={() => server.faults.push("403")}
          />
          <Button
            title="Långsamma svar · 3 sekunder"
            secondary
            onPress={() => {
              server.latency = 3000;
            }}
          />
          <Button
            title="Normal svarstid"
            secondary
            onPress={() => {
              server.latency = 250;
            }}
          />
        </View>
      )}
    </Screen>
  );
}
