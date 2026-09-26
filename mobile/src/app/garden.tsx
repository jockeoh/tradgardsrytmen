import { useState } from "react";
import { Text, View } from "react-native";
import { Redirect, router } from "expo-router";
import { Garden, Plant, Task, gardenPath } from "../api/contract";
import { useSession } from "../core/runtime";
import {
  Button,
  ErrorPanel,
  Loading,
  PagedList,
  Screen,
  styles,
  useResource,
} from "../ui/common";
export default function GardenRoute() {
  const session = useSession();
  return session.garden ? (
    <GardenScreen key={session.epoch} />
  ) : (
    <Redirect href="/" />
  );
}
function GardenScreen() {
  const session = useSession(),
    path = gardenPath(session.garden!);
  const garden = useResource<Garden>(path);
  const [tab, setTab] = useState<"pending" | "plants" | "history">("pending");
  const [historyStatus, setHistoryStatus] = useState<
    "completed" | "skipped" | "archived"
  >("completed");
  return (
    <Screen
      title={garden.data?.name ?? "Din trädgård"}
      back={() => {
        session.selectGarden(null);
        router.replace("/");
      }}
    >
      {garden.loading && <Loading />}
      <ErrorPanel error={garden.error} retry={garden.reload} />
      <View style={styles.row}>
        {(["pending", "plants", "history"] as const).map((t) => (
          <Button
            key={t}
            title={
              { pending: "Att göra", plants: "Växter", history: "Historik" }[t]
            }
            secondary={tab !== t}
            onPress={() => setTab(t)}
          />
        ))}
      </View>
      {tab === "plants" ? (
        <>
          <Button
            title="Lägg till växt"
            onPress={() =>
              router.push({ pathname: "/new", params: { kind: "plant" } })
            }
          />
          <PagedList<Plant>
            path={path + "plants/"}
            empty="Inga växter ännu. Lägg till en växt för att komma igång."
            render={(plant) => (
              <View style={styles.card}>
                <Text style={styles.label}>{plant.name}</Text>
                <Text style={styles.muted}>
                  {plant.has_care_plan
                    ? "Skötselplan finns"
                    : "Saknar skötselplan · manuella uppgifter går bra"}
                </Text>
                <Button
                  title={`Visa ${plant.name}`}
                  secondary
                  onPress={() =>
                    router.push({
                      pathname: "/plant",
                      params: { id: plant.id },
                    })
                  }
                />
              </View>
            )}
          />
        </>
      ) : (
        <>
          <Text style={styles.text}>
            {tab === "pending"
              ? "Välj en uppgift att ta hand om."
              : "Sparade uppgifter, även äldre och arkiverade."}
          </Text>
          {tab === "history" && (
            <View style={styles.row}>
              {(["completed", "skipped", "archived"] as const).map((status) => (
                <Button
                  key={status}
                  title={statusLabel(status)}
                  secondary={historyStatus !== status}
                  onPress={() => setHistoryStatus(status)}
                />
              ))}
            </View>
          )}
          <PagedList<Task>
            key={tab + historyStatus}
            path={
              path +
              "tasks/?status=" +
              (tab === "pending" ? "pending" : historyStatus)
            }
            empty={
              tab === "pending"
                ? "Inga väntande uppgifter. Det säger inte om växterna har kompletta skötselplaner."
                : "Ingen uppgift sparad ännu."
            }
            render={(task) => (
              <View style={styles.card}>
                <Text style={styles.label}>{task.title}</Text>
                <Text style={styles.muted}>
                  {task.due_date} · {statusLabel(task.status)}
                </Text>
                <Button
                  title={`Öppna ${task.title}`}
                  secondary
                  onPress={() =>
                    router.push({ pathname: "/task", params: { id: task.id } })
                  }
                />
              </View>
            )}
          />
          <Button
            title="Skapa manuell uppgift"
            secondary
            onPress={() => {
              setTab("plants");
            }}
          />
          <Text style={styles.muted}>Välj växt för att skapa en uppgift.</Text>
        </>
      )}
    </Screen>
  );
}
export function statusLabel(status: Task["status"]) {
  return {
    pending: "Att göra",
    completed: "Utförd",
    skipped: "Överhoppad",
    archived: "Arkiverad",
  }[status];
}
