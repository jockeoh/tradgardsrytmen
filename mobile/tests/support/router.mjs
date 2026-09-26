import { useEffect } from "react";
export let params = {};
export const navigation = [];
export function setParams(value) {
  params = value;
  navigation.length = 0;
}
export function useLocalSearchParams() {
  return params;
}
export function useFocusEffect(callback) {
  useEffect(callback, [callback]);
}
export const router = {
  replace: (value) => navigation.push(value),
  push: (value) => navigation.push(value),
};
export function Redirect() {
  return null;
}
