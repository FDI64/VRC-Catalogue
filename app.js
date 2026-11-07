const { createApp, ref, computed, onMounted } = Vue;

createApp({
  setup() {
    // 🔐 인증 상태
    const isAuthenticated = ref(false);
    const authNeedsSetup = ref(false);
    const setupPasswordInput = ref('');
    const loginPasswordInput = ref('');
    const authError = ref('');
    const authSubmitting = ref(false);

    // 🏷️ 필터 및 정렬 상태
    const avatars = ref([]);
    const categories = ref([]);
    const selectedAvatar = ref(248); // 마누카 기본값
    const selectedCategory = ref(null);
    const maOnly = ref(false);
    const adultMode = ref('all'); // 'all', 'safe', 'r18'
    const sortBy = ref('likes');

    // 🌐 번역 상태
    const translateToKo = ref(false);
    const isHotTranslating = ref(false);

    // 🔍 텍스트 검색 및 다중 태그 상태
    const searchType = ref('shop');
    const keywordInput = ref('');
    const appliedKeyword = ref('');
    const tagQuery = ref('');
    const tagSuggestions = ref([]);
    const selectedTags = ref([]);
    let tagDebounceTimer = null;

    // 📦 아이템 목록 및 페이지네이션
    const items = ref([]);
    const loading = ref(false);
    const offset = ref(0);
    const limit = 12;

    // ⚡ 신규 에셋 동기화 상태
    const showSyncConfirm = ref(false);
    const syncInfo = ref({
      is_running: false,
      progress_msg: '대기 중',
      new_count: 0
    });
    let syncPollTimer = null;

    // --- Computed 계산 속성 ---
    const sortLabel = computed(() => {
      const map = {
        likes: '🔥 좋아요순',
        trending: '⚡ 트렌딩',
        newest: '🕒 최신순',
        price_asc: '💵 낮은가격순',
        price_desc: '💎 높은가격순'
      };
      return map[sortBy.value] || '정렬';
    });

    const currentAvatarName = computed(() => {
      if (!selectedAvatar.value) return '전체';
      const av = avatars.value.find(a => a.avatar_id === selectedAvatar.value);
      return av ? (av.name_ko || av.name_ja) : '선택됨';
    });

    const currentCategoryName = computed(() => {
      if (!selectedCategory.value) return '전체';
      const cat = categories.value.find(c => c.category_id === selectedCategory.value);
      return cat ? (cat.name_ko || cat.name_ja || cat.name_en) : '전체';
    });

    // 📅 날짜 포맷팅 (00.00.00)
    const formatReleaseDate = (dateStr) => {
      if (!dateStr) return '';
      try {
        const d = new Date(dateStr);
        const yy = String(d.getFullYear()).slice(-2);
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        return `${yy}.${mm}.${dd}`;
      } catch {
        return dateStr.slice(2, 10).replace(/-/g, '.');
      }
    };

    // --- 🔐 인증 관련 메소드 ---
    const checkAuth = async () => {
      try {
        const res = await fetch('/api/auth/status');
        const data = await res.json();
        authNeedsSetup.value = data.needs_setup;
        isAuthenticated.value = data.is_authenticated;

        if (isAuthenticated.value) {
          initApp();
        }
      } catch (e) {
        console.error('인증 상태 확인 실패:', e);
      }
    };

    const handleSetupPassword = async () => {
      authError.value = '';
      authSubmitting.value = true;
      try {
        const res = await fetch('/api/auth/setup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: setupPasswordInput.value })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || '설정 실패');

        authNeedsSetup.value = false;
        isAuthenticated.value = true;
        initApp();
      } catch (e) {
        authError.value = e.message;
      } finally {
        authSubmitting.value = false;
      }
    };

    const handleLogin = async () => {
      authError.value = '';
      authSubmitting.value = true;
      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: loginPasswordInput.value })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || '인증 실패');

        isAuthenticated.value = true;
        initApp();
      } catch (e) {
        authError.value = e.message;
      } finally {
        authSubmitting.value = false;
      }
    };

    const handleLogout = async () => {
      await fetch('/api/auth/logout', { method: 'POST' });
      isAuthenticated.value = false;
      loginPasswordInput.value = '';
      authError.value = '';
    };

    // --- 🏷️ 필터링 및 조작 메소드 ---
    const setAdultMode = (mode) => {
      adultMode.value = mode;
      onFilterChange();
    };

    const onFilterChange = () => {
      offset.value = 0;
      fetchItems(false);
    };

    const selectCategory = (catId) => {
      selectedCategory.value = catId;
      onFilterChange();
    };

    const applySearch = () => {
      appliedKeyword.value = keywordInput.value.trim();
      onFilterChange();
    };

    const clearSearch = () => {
      keywordInput.value = '';
      appliedKeyword.value = '';
      onFilterChange();
    };

    const loadMore = () => {
      offset.value += limit;
      fetchItems(true);
    };

    // --- 🏷️ 태그 조작 메소드 ---
    const onTagInput = () => {
      clearTimeout(tagDebounceTimer);
      const q = tagQuery.value.trim();
      if (!q) {
        tagSuggestions.value = [];
        return;
      }

      tagDebounceTimer = setTimeout(async () => {
        try {
          const res = await fetch(`/api/tags?q=${encodeURIComponent(q)}`);
          tagSuggestions.value = await res.json();
        } catch (e) {
          console.error('태그 검색 실패:', e);
        }
      }, 250);
    };

    const addTag = (tagObj, mode) => {
      const exists = selectedTags.value.find(t => t.tag_id === tagObj.tag_id);
      const displayName = tagObj.name_ko && tagObj.name_ko !== tagObj.name 
        ? `${tagObj.name_ko} (${tagObj.name})` 
        : tagObj.name;

      if (exists) {
        exists.mode = mode;
      } else {
        selectedTags.value.push({
          tag_id: tagObj.tag_id,
          name: tagObj.name,
          display_name: displayName,
          mode: mode
        });
      }

      tagQuery.value = '';
      tagSuggestions.value = [];
      onFilterChange();
    };

    const toggleTagMode = (st) => {
      st.mode = st.mode === 'include' ? 'exclude' : 'include';
      onFilterChange();
    };

    const removeTag = (tagId) => {
      selectedTags.value = selectedTags.value.filter(t => t.tag_id !== tagId);
      onFilterChange();
    };

    const clearAllTags = () => {
      selectedTags.value = [];
      onFilterChange();
    };

    // --- 🌐 번역 핫로딩 메소드 ---
    const toggleTranslation = async () => {
      translateToKo.value = !translateToKo.value;
      if (!translateToKo.value) return;

      const missing = items.value.filter(it => !it.title_ko);
      if (missing.length === 0) return;

      isHotTranslating.value = true;
      try {
        const ids = missing.map(it => it.item_id).join(',');
        const res = await fetch(`/api/translate-items?item_ids=${ids}`);
        const data = await res.json();
        
        if (data.translations) {
          for (const it of items.value) {
            if (data.translations[it.item_id]) {
              it.title_ko = data.translations[it.item_id];
            }
          }
        }
      } catch (e) {
        console.error('핫로딩 번역 실패:', e);
      } finally {
        isHotTranslating.value = false;
      }
    };

    // --- 📦 데이터 페치 메소드 ---
    const fetchAvatars = async () => {
      try {
        const res = await fetch('/api/avatars');
        if (res.status === 401) { isAuthenticated.value = false; return; }
        avatars.value = await res.json();
      } catch (e) {
        console.error('아바타 로드 실패:', e);
      }
    };

    const fetchCategories = async () => {
      try {
        const res = await fetch('/api/categories');
        if (res.status === 401) { isAuthenticated.value = false; return; }
        categories.value = await res.json();
      } catch (e) {
        console.error('카테고리 로드 실패:', e);
      }
    };

    const fetchItems = async (isAppend = false) => {
      loading.value = true;
      try {
        let url = `/api/items?limit=${limit}&offset=${offset.value}&ma_only=${maOnly.value}&adult_mode=${adultMode.value}&sort_by=${sortBy.value}&translate=${translateToKo.value}`;
        if (selectedAvatar.value) url += `&avatar_id=${selectedAvatar.value}`;
        if (selectedCategory.value) url += `&category_id=${selectedCategory.value}`;
        if (appliedKeyword.value) {
          url += `&search_type=${searchType.value}&keyword=${encodeURIComponent(appliedKeyword.value)}`;
        }

        const incIds = selectedTags.value.filter(t => t.mode === 'include').map(t => t.tag_id);
        const excIds = selectedTags.value.filter(t => t.mode === 'exclude').map(t => t.tag_id);
        if (incIds.length > 0) url += `&include_tags=${incIds.join(',')}`;
        if (excIds.length > 0) url += `&exclude_tags=${excIds.join(',')}`;

        const res = await fetch(url);
        if (res.status === 401) { isAuthenticated.value = false; return; }
        const data = await res.json();

        if (isAppend) {
          items.value.push(...data.items);
        } else {
          items.value = data.items;
        }
      } catch (e) {
        console.error('아이템 로드 실패:', e);
      } finally {
        loading.value = false;
      }
    };

    // --- ⚡ 동기화 메소드 ---
    const checkSyncStatus = async () => {
      try {
        const res = await fetch('/api/sync-status');
        if (res.status === 401) return;
        const data = await res.json();
        const wasRunning = syncInfo.value.is_running;
        syncInfo.value = data;

        if (wasRunning && !data.is_running && data.new_count > 0) {
          fetchItems(false);
        }
      } catch (e) {
        console.error('동기화 상태 조회 실패:', e);
      }
    };

    const startManualSync = async () => {
      showSyncConfirm.value = false;
      try {
        await fetch('/api/sync-new-items', { method: 'POST' });
        checkSyncStatus();
        if (!syncPollTimer) {
          syncPollTimer = setInterval(checkSyncStatus, 1500);
        }
      } catch (e) {
        console.error('동기화 시작 실패:', e);
      }
    };

    // 초기화
    const initApp = async () => {
      await Promise.all([fetchAvatars(), fetchCategories()]);
      await fetchItems(false);
      checkSyncStatus();
      if (!syncPollTimer) {
        syncPollTimer = setInterval(checkSyncStatus, 2000);
      }
    };

    onMounted(() => {
      checkAuth();
    });

    return {
      isAuthenticated,
      authNeedsSetup,
      setupPasswordInput,
      loginPasswordInput,
      authError,
      authSubmitting,
      handleSetupPassword,
      handleLogin,
      handleLogout,
      avatars,
      categories,
      selectedAvatar,
      selectedCategory,
      maOnly,
      adultMode,
      setAdultMode,
      sortBy,
      sortLabel,
      translateToKo,
      isHotTranslating,
      toggleTranslation,
      searchType,
      keywordInput,
      appliedKeyword,
      tagQuery,
      tagSuggestions,
      selectedTags,
      currentAvatarName,
      currentCategoryName,
      formatReleaseDate,
      showSyncConfirm,
      syncInfo,
      startManualSync,
      items,
      loading,
      onFilterChange,
      selectCategory,
      applySearch,
      clearSearch,
      onTagInput,
      addTag,
      toggleTagMode,
      removeTag,
      clearAllTags,
      loadMore
    };
  }
}).mount('#app');