import { Platform } from 'react-native';
import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import { journalStore } from '../core/storage';
// Registration is only called from an explicit button, never from render/startup.
export async function notificationToken(scopeKey:string,register:boolean):Promise<string>{
 const key=`garden-native-notifications:${scopeKey}`;
 if(!register){const saved=await journalStore.getItem(key);if(!saved)throw new Error('Ingen enhetsregistrering finns sparad här.');return saved;}
 if(Platform.OS==='web')throw new Error('Mobilnotiser aktiveras i den installerade appen.');
 const projectId=Constants.expoConfig?.extra?.eas?.projectId??Constants.easConfig?.projectId;
 if(typeof projectId!=='string'||!projectId)throw new Error('Notiser kan aktiveras när appens installation är konfigurerad.');
 if(Platform.OS==='android')await Notifications.setNotificationChannelAsync('garden',{name:'Trädgården',importance:Notifications.AndroidImportance.DEFAULT});
 const existing=await Notifications.getPermissionsAsync();
 const permission=existing.status==='granted'?existing:await Notifications.requestPermissionsAsync();
 if(permission.status!=='granted')throw new Error('Tillåt notiser i telefonens inställningar för att aktivera påminnelser.');
 const token=(await Notifications.getExpoPushTokenAsync({projectId})).data;
 await journalStore.setItem(key,token);return token;
}
