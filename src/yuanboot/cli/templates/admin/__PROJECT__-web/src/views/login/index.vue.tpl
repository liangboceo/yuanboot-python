<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { useRouter, useRoute } from "vue-router";
import { message } from "@/utils/message";
import { getCaptcha } from "@/api/user";
import { getSystemConfig } from "@/api/system-config";
import { loginRules } from "./utils/rule";
import { debounce } from "@pureadmin/utils";
import { useNav } from "@/layout/hooks/useNav";
import { useEventListener } from "@vueuse/core";
import type { FormInstance } from "element-plus";
import { $t, transformI18n } from "@/plugins/i18n";
import { useLayout } from "@/layout/hooks/useLayout";
import { useUserStoreHook } from "@/store/modules/user";
import { initRouter, getTopMenu } from "@/router/utils";
import { ref, reactive, watch, computed, onMounted } from "vue";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { useTranslationLang } from "@/layout/hooks/useTranslationLang";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";

import dayIcon from "@/assets/svg/day.svg?component";
import darkIcon from "@/assets/svg/dark.svg?component";
import globalization from "@/assets/svg/globalization.svg?component";
import Lock from "~icons/ri/lock-fill";
import Check from "~icons/ep/check";
import User from "~icons/ri/user-3-fill";
import Info from "~icons/ri/information-line";
import Keyhole from "~icons/ri/shield-keyhole-line";

defineOptions({
  name: "Login"
});

const captchaImage = ref("");
const captchaLoading = ref(false);
const loginDay = ref(7);
const router = useRouter();
const route = useRoute();
const loading = ref(false);
const checked = ref(false);
const disabled = ref(false);
const ruleFormRef = ref<FormInstance>();

// 从系统配置加载的品牌信息
const sysName = ref("Yuanboot Admin");
const sysLogo = ref("");
const sysTitle = ref("Yuanboot Admin");
const sysDescription = ref("基于 yuanboot-python 的后台管理系统");

const { t } = useI18n();
const { initStorage } = useLayout();
initStorage();
const { dataTheme, themeMode, dataThemeChange } = useDataThemeChange();
dataThemeChange(themeMode.value);
const { title, getDropdownItemStyle, getDropdownItemClass } = useNav();
const { locale, translationCh, translationEn } = useTranslationLang();

const ruleForm = reactive({
  username: "",
  password: "",
  verifyCode: "",
  captchaId: ""
});

// 加载系统配置
async function loadSystemConfig() {
  try {
    const nameResult = (await getSystemConfig({
      configKey: "system_name"
    })) as any;
    const nameData = nameResult?.data ?? nameResult;
    if (nameData?.configValue) sysName.value = nameData.configValue;

    const logoResult = (await getSystemConfig({
      configKey: "system_logo"
    })) as any;
    const logoData = logoResult?.data ?? logoResult;
    if (logoData?.configValue) sysLogo.value = logoData.configValue;

    const titleResult = (await getSystemConfig({
      configKey: "system_title"
    })) as any;
    const titleData = titleResult?.data ?? titleResult;
    if (titleData?.configValue) sysTitle.value = titleData.configValue;

    const descResult = (await getSystemConfig({
      configKey: "system_description"
    })) as any;
    const descData = descResult?.data ?? descResult;
    if (descData?.configValue) sysDescription.value = descData.configValue;
  } catch {
    // 加载失败使用默认值
  }
}

async function loadCaptcha() {
  captchaLoading.value = true;
  try {
    const data = await getCaptcha();
    ruleForm.captchaId = data.captchaId;
    captchaImage.value = data.image;
    ruleForm.verifyCode = "";
  } finally {
    captchaLoading.value = false;
  }
}

const onLogin = async (formEl: FormInstance | undefined) => {
  if (!formEl) return;
  await formEl.validate(valid => {
    if (valid) {
      loading.value = true;
      useUserStoreHook()
        .loginByUsername({
          username: ruleForm.username,
          password: ruleForm.password,
          verifyCode: ruleForm.verifyCode,
          captchaId: ruleForm.captchaId
        })
        .then(async () => {
          const dynamicRouter = (await initRouter()) as any;
          disabled.value = true;
          message(t("login.pureLoginSuccess"), { type: "success" });
          const rawReturnUrl = Array.isArray(route.query.return_url)
            ? route.query.return_url[0]
            : route.query.return_url;
          const topMenu = getTopMenu(true);
          const redirectPath =
            typeof rawReturnUrl === "string" &&
            rawReturnUrl &&
            !rawReturnUrl.startsWith("/login")
              ? rawReturnUrl
              : topMenu?.path || "/";
          try {
            await dynamicRouter.replace(redirectPath);
          } catch {
            await dynamicRouter.replace(topMenu?.path || "/");
          }
        })
        .catch(() => {
          loadCaptcha();
        })
        .finally(() => {
          disabled.value = false;
          loading.value = false;
        });
    }
  });
};

const immediateDebounce: any = debounce(
  formRef => onLogin(formRef),
  1000,
  true
);

useEventListener(document, "keydown", ({ code }) => {
  if (
    ["Enter", "NumpadEnter"].includes(code) &&
    !disabled.value &&
    !loading.value
  )
    immediateDebounce(ruleFormRef.value);
});

onMounted(() => {
  loadCaptcha();
  loadSystemConfig();
});
watch(checked, bool => {
  useUserStoreHook().SET_ISREMEMBERED(bool);
});
watch(loginDay, value => {
  useUserStoreHook().SET_LOGINDAY(value);
});
</script>

<template>
  <div class="login-page select-none">
    <!-- 左上角 Logo -->
    <div class="top-logo">
      <!-- 自定义上传的Logo（base64 图片） -->
      <img v-if="sysLogo" :src="sysLogo" class="logo-img-custom" alt="logo" />
      <!-- 默认Logo SVG -->
      <svg v-else class="logo-icon" viewBox="0 0 24 24" fill="none">
        <path
          d="M12 2L3 7v10l9 5 9-5V7L12 2z"
          fill="#e8f0fe"
          stroke="#3370ff"
          stroke-width="1.5"
          stroke-linejoin="round"
        />
        <path d="M12 22V12" stroke="#3370ff" stroke-width="1.5" />
        <path
          d="M12 12L3 7"
          stroke="#3370ff"
          stroke-width="1.5"
          stroke-linejoin="round"
        />
        <path
          d="M12 12l9-5"
          stroke="#3370ff"
          stroke-width="1.5"
          stroke-linejoin="round"
        />
        <path d="M6 10v4l6 3" stroke="#3370ff" stroke-width="1" opacity="0.5" />
      </svg>
      <span>{{ sysName }}</span>
    </div>

    <!-- 右上角工具栏 -->
    <div class="top-toolbar">
      <el-dropdown trigger="click">
        <globalization
          class="hover:text-primary hover:bg-transparent! size-5 cursor-pointer outline-hidden duration-300"
        />
        <template #dropdown>
          <el-dropdown-menu class="translation">
            <el-dropdown-item
              :style="getDropdownItemStyle(locale, 'zh')"
              :class="['dark:text-white!', getDropdownItemClass(locale, 'zh')]"
              @click="translationCh"
            >
              <IconifyIconOffline
                v-show="locale === 'zh'"
                class="check-zh"
                :icon="Check"
              />
              简体中文
            </el-dropdown-item>
            <el-dropdown-item
              :style="getDropdownItemStyle(locale, 'en')"
              :class="['dark:text-white!', getDropdownItemClass(locale, 'en')]"
              @click="translationEn"
            >
              <span v-show="locale === 'en'" class="check-en">
                <IconifyIconOffline :icon="Check" />
              </span>
              English
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <el-switch
        v-model="dataTheme"
        inline-prompt
        :active-icon="dayIcon"
        :inactive-icon="darkIcon"
        @change="dataThemeChange"
      />
    </div>

    <div class="login-container">
      <!-- 左侧品牌区域 -->
      <div class="brand-section">
        <h1 class="brand-title">
          {{ sysTitle }}
        </h1>
        <p class="brand-subtitle">{{ sysDescription }}</p>

        <div class="features-grid">
          <div class="feature-card">
            <div class="feature-icon">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              >
                <path d="M12 20V10" />
                <path d="M18 20V4" />
                <path d="M6 20v-4" />
              </svg>
            </div>
            <div class="feature-title">用户与部门</div>
            <div class="feature-desc">维护用户账号、所属部门及启用状态，支持密码重置与头像设置。</div>
          </div>

          <div class="feature-card">
            <div class="feature-icon">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              >
                <polyline points="16,18 22,12 16,6" />
                <polyline points="8,6 2,12 8,18" />
              </svg>
            </div>
            <div class="feature-title">角色与菜单</div>
            <div class="feature-desc">分配角色、动态菜单与按钮权限，按部门和角色控制数据访问范围。</div>
          </div>

          <div class="feature-card">
            <div class="feature-icon">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              >
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22,4 12,14.01 9,11.01" />
              </svg>
            </div>
            <div class="feature-title">系统配置</div>
            <div class="feature-desc">集中管理系统名称、标识与宣传语，配置修改后持久保存。</div>
          </div>

          <div class="feature-card">
            <div class="feature-icon">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              >
                <circle cx="12" cy="12" r="10" />
                <polyline points="12,6 12,12 16,14" />
              </svg>
            </div>
            <div class="feature-title">运行与监控</div>
            <div class="feature-desc">提供健康检查、结构化日志和监控指标，便于查看服务运行状态。</div>
          </div>
        </div>
      </div>

      <!-- 右侧登录卡片 -->
      <div class="login-box">
        <div class="login-card">
          <h2 class="login-card-title">欢迎来到 {{ sysName }}</h2>

          <!-- 登录表单 -->
          <el-form
            ref="ruleFormRef"
            :model="ruleForm"
            :rules="loginRules"
            size="large"
            class="login-form"
            autocomplete="off"
          >
            <el-form-item
              :rules="[
                {
                  required: true,
                  message: transformI18n($t('login.pureUsernameReg')),
                  trigger: 'blur'
                }
              ]"
              prop="username"
            >
              <el-input
                v-model="ruleForm.username"
                clearable
                :placeholder="'请输入用户名'"
                :prefix-icon="useRenderIcon(User)"
                autocomplete="off"
              />
            </el-form-item>

            <el-form-item prop="password">
              <el-input
                v-model="ruleForm.password"
                clearable
                show-password
                :placeholder="'请输入密码'"
                :prefix-icon="useRenderIcon(Lock)"
                autocomplete="new-password"
              />
            </el-form-item>

            <el-form-item prop="verifyCode">
              <el-input
                v-model="ruleForm.verifyCode"
                clearable
                :placeholder="'请输入验证码'"
                :prefix-icon="useRenderIcon(Keyhole)"
                autocomplete="off"
              >
                <template #append>
                  <div
                    v-loading="captchaLoading"
                    class="captcha-wrap bg-white"
                    style="width: 120px; background: #f5f5f5"
                    @click="loadCaptcha"
                  >
                    <img
                      v-if="captchaImage"
                      :src="captchaImage"
                      style="width: 100%; height: 100%"
                      alt="验证码"
                    />
                  </div>
                </template>
              </el-input>
            </el-form-item>

            <el-form-item>
              <div class="w-full h-5 flex-bc login-options">
                <el-checkbox v-model="checked">
                  <span class="flex">
                    <select
                      v-model="loginDay"
                      :style="{
                        width: loginDay < 10 ? '10px' : '16px',
                        outline: 'none',
                        background: 'none',
                        appearance: 'none',
                        border: 'none'
                      }"
                    >
                      <option value="1">1</option>
                      <option value="7">7</option>
                      <option value="30">30</option>
                    </select>
                    {{ t("login.pureRemember") }}
                    <IconifyIconOffline
                      v-tippy="{
                        content: t('login.pureRememberInfo'),
                        placement: 'top'
                      }"
                      :icon="Info"
                      class="ml-1"
                    />
                  </span>
                </el-checkbox>
              </div>

              <el-button
                class="w-full mt-4!"
                size="default"
                type="primary"
                :loading="loading"
                :disabled="disabled"
                @click="onLogin(ruleFormRef)"
              >
                登 录
              </el-button>

            </el-form-item>
          </el-form>
        </div>
      </div>
    </div>

    <!-- 页面底部版权 -->
    <div class="page-footer">
      Copyright (c) 2026 jackson liang
    </div>
  </div>
</template>

<style scoped>
@import url("@/style/login.css");

:deep(.el-input-group__append, .el-input-group__prepend) {
  padding: 0;
}

.translation {
  :deep(.el-dropdown-menu__item) {
    padding: 5px 40px;
  }

  .check-zh {
    position: absolute;
    left: 20px;
  }

  .check-en {
    position: absolute;
    left: 20px;
  }
}

/* 自定义上传 Logo 图片样式 */
.logo-img-custom {
  width: 28px;
  height: 28px;
  object-fit: contain;
}
</style>
