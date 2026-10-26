import type { IconifyIcon as IconifyData } from "@iconify/types";
import { h, defineComponent } from "vue";
import { Icon as IconifyIcon } from "@iconify/vue/dist/offline";

// Iconify Icon在Vue里本地使用（用于内网环境）
export default defineComponent({
  name: "IconifyIconOffline",
  components: { IconifyIcon },
  props: {
    icon: {
      default: null
    }
  },
  render() {
    const attrs = this.$attrs;
    if (typeof this.icon === "string" || (this.icon && typeof this.icon === "object" && "body" in this.icon)) {
      return h(
        IconifyIcon,
        {
          icon: this.icon as string | IconifyData,
          "aria-hidden": false,
          style: attrs?.style
            ? Object.assign(attrs.style, { outline: "none" })
            : { outline: "none" },
          ...attrs
        },
        {
          default: () => []
        }
      );
    } else {
      return h(
        this.icon,
        {
          "aria-hidden": false,
          style: attrs?.style
            ? Object.assign(attrs.style, { outline: "none" })
            : { outline: "none" },
          ...attrs
        },
        {
          default: () => []
        }
      );
    }
  }
});
