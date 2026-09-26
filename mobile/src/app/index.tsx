import { useState } from "react";
import { Text, View } from "react-native";
import { router } from "expo-router";
import { Garden } from "../api/contract";
import { accounts } from "../api/fixtures";
import { server, useSession } from "../core/runtime";
import { Button, PagedList, Screen, styles } from "../ui/common";
export default function Home() {
  const session = useSession();
  const [tools, setTools] = useState(false);
  return (
    <Screen title={session.account ? "Dina trädgårdar" : "En sak i taget."}>
      {session.notice ? (
        <Text accessibilityRole="alert" style={styles.text}>
          {session.notice}
        </Text>
      ) : null}
      {!session.account ? (
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
            onPress={() => session.logout()}
          />
        </>
      )}
      <Button
        title={tools ? "Dölj provverktyg" : "Visa provverktyg"}
        secondary
        onPress={() => setTools(!tools)}
      />
      {tools && (
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
