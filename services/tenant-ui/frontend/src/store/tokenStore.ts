import { defineStore } from 'pinia';
import { Ref, ref } from 'vue';
import axios from 'axios';
import { useConfigStore } from './configStore';
import { API_PATH } from '@/helpers/constants';

export const useTokenStore = defineStore('token', () => {
  // state
  const token: Ref<string | null> = ref(null);
  const loading: any = ref(false);
  const error: any = ref(null);

  // getters

  // actions
  async function login(username: string, password: string) {
    console.log('> tokenStore.load');
    const payload = {
      wallet_key: password,
    };
    token.value = null;
    error.value = null;
    loading.value = true;

    // TODO: isolate this to something reusable when we grab an axios connection.
    const configStore = useConfigStore();
    const url = configStore.proxyPath(
      API_PATH.MULTITENANCY_WALLET_TOKEN(username)
    );
    await axios({
      method: 'post',
      url,
      data: payload,
    })
      .then((res) => {
        console.log(res);
        token.value = res.data.token;
      })
      .catch((err) => {
        error.value = err;
        console.log(error.value);
      })
      .finally(() => {
        loading.value = false;
      });
    console.log('< tokenStore.load');

    if (error.value != null) {
      // throw error so $onAction.onError listeners can add their own handler
      throw error.value;
    }
    // return data so $onAction.after listeners can add their own handler
    return token.value;
  }

  function clearToken() {
    console.log('> clearToken');
    token.value = null;
    console.log('< clearToken');
  }

  return { token, loading, error, clearToken, login };
});

export default {
  useTokenStore,
};
