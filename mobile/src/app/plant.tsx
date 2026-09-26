import { Text, View } from "react-native";
import { Redirect, router, useLocalSearchParams } from "expo-router";
import { Plant, Task, gardenPath } from "../api/contract";
import { useSession } from "../core/runtime";
import {
  Button,
  ErrorPanel,
  Loading,
  PagedList,
  Screen,
  backToGarden,
  styles,
  useResource,
} from "../ui/common";
export default function PlantRoute() {
  const session = useSession();
  const { id } = useLocalSearchParams<{ id: string }>();
  return session.garden && typeof id === "string" ? (
    <PlantScreen key={session.epoch + id} id={id} />
  ) : (
    <Redirect href="/" />
  );
}
function PlantScreen({ id }: { id: string }) {
  const session = useSession(),
    path = gardenPath(session.garden!);
  const plant = useResource<Plant>(
    path + "plants/" + encodeURIComponent(id) + "/",
  );
  return (
    <Screen title={plant.data?.name ?? "Växt"} back={backToGarden}>
      {plant.loading && <Loading />}
      <ErrorPanel error={plant.error} retry={plant.reload} />
      {plant.data && (
        <>
          <Text style={styles.text}>
            {plant.data.notes || "Inga anteckningar."}
          </Text>
          <Text style={styles.muted}>
            {plant.data.has_care_plan
              ? "Skötselplan finns."
              : "Ingen skötselplan. Du kan själv lägga till en uppgift."}
          </Text>
          <Button
            title="Lägg till uppgift"
            onPress={() =>
              router.push({
                pathname: "/new",
                params: { kind: "task", plant: id },
              })
            }
          />
          <Text style={styles.label}>Växtens uppgifter</Text>
          <PagedList<Task>
            path={path + "tasks/?plant_id=" + encodeURIComponent(id)}
            empty="Inga uppgifter för den här växten."
            render={(task) => (
              <View style={styles.card}>
                <Text style={styles.text}>{task.title}</Text>
                <Text style={styles.muted}>{task.due_date}</Text>
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
          <Text style={styles.muted}>
            Redigering av sparade växter stöds ännu inte i mobilens API.
          </Text>
        </>
      )}
    </Screen>
  );
}
