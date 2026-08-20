import { definePreset } from '@primevue/themes';
import Aura from '@primevue/themes/aura';

/**
 * Bard's palette, taken from the app icon: a black lyre on #1DB954.
 *
 * The app is dark-only, so every token is written as a flat value rather than
 * a light-dark() pair — main.ts pins the dark colour scheme with a class, and
 * a single set of values keeps what you read here identical to what renders.
 */

/**
 * 500 is the icon's exact green and 400 its lighter hover twin; the rest of the
 * ramp is built around that pair rather than the other way round, so the brand
 * colour is a value in the file and not something derived and approximate.
 */
const green = {
  50: '#e9fbf0',
  100: '#c7f5d9',
  200: '#8eeab3',
  300: '#52dd8b',
  400: '#1ed760',
  500: '#1db954',
  600: '#189a46',
  700: '#147a38',
  800: '#12602d',
  900: '#0f4c25',
  950: '#062a13',
};

/**
 * Near-neutral greys carrying a trace of the icon's green, so the chrome sits
 * under the accent instead of arguing with it. 950 is the app floor; 0 is
 * reserved for pure white text.
 */
const shade = {
  0: '#ffffff',
  50: '#f4f7f5',
  100: '#e4eae6',
  200: '#c6cfc9',
  300: '#a2aca6',
  400: '#7a847e',
  500: '#5c6661',
  600: '#434c47',
  700: '#2d3531',
  800: '#1e2421',
  900: '#131816',
  950: '#0a0e0c',
};

/** The accent at the alphas used for fills, selections and glows. */
const accent = (alpha: number) => `rgba(29, 185, 84, ${alpha})`;

export const BardPreset = definePreset(Aura, {
  primitive: {
    borderRadius: {
      none: '0',
      xs: '4px',
      sm: '6px',
      md: '8px',
      lg: '12px',
      xl: '16px',
    },
  },
  semantic: {
    transitionDuration: '0.15s',
    focusRing: {
      width: '2px',
      style: 'solid',
      color: '{primary.500}',
      offset: '2px',
      shadow: 'none',
    },
    primary: green,
    colorScheme: {
      dark: {
        primary: {
          // The icon's green exactly, with its lighter neighbours for the
          // hover and active steps.
          color: '{primary.500}',
          // Black, as on the icon itself.
          contrastColor: '#000000',
          hoverColor: '{primary.400}',
          activeColor: '{primary.300}',
        },
        surface: shade,
        text: {
          color: '{surface.50}',
          hoverColor: '{surface.0}',
          mutedColor: '{surface.400}',
          hoverMutedColor: '{surface.300}',
        },
        content: {
          background: 'rgba(255, 255, 255, 0.04)',
          hoverBackground: 'rgba(255, 255, 255, 0.07)',
          borderColor: 'rgba(255, 255, 255, 0.08)',
        },
        overlay: {
          select: {
            background: '#181d1a',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            color: '{surface.50}',
          },
          popover: {
            background: '#181d1a',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            color: '{surface.50}',
          },
          modal: {
            background: '#151a17',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            color: '{surface.50}',
          },
        },
        list: {
          option: {
            focusBackground: 'rgba(255, 255, 255, 0.07)',
            selectedBackground: accent(0.16),
            selectedColor: '{primary.400}',
          },
        },
        formField: {
          background: 'rgba(255, 255, 255, 0.05)',
          disabledBackground: 'rgba(255, 255, 255, 0.03)',
          filledBackground: 'rgba(255, 255, 255, 0.05)',
          filledHoverBackground: 'rgba(255, 255, 255, 0.07)',
          filledFocusBackground: 'rgba(255, 255, 255, 0.07)',
          borderColor: 'rgba(255, 255, 255, 0.1)',
          hoverBorderColor: 'rgba(255, 255, 255, 0.2)',
          focusBorderColor: '{primary.500}',
          color: '{surface.50}',
          placeholderColor: '{surface.500}',
          floatLabelColor: '{surface.400}',
          shadow: 'none',
        },
        mask: {
          background: 'rgba(6, 9, 7, 0.72)',
        },
      },
    },
  },
  components: {
    button: {
      root: {
        gap: '0.5rem',
        paddingX: '1rem',
        paddingY: '0.5rem',
        borderRadius: '999px',
        label: { fontWeight: '700' },
      },
    },
    toast: {
      root: { borderWidth: '1px', width: '22rem' },
      content: { padding: '0.85rem 1rem' },
      text: { gap: '0.25rem' },
      summary: { fontWeight: '650', fontSize: '0.875rem' },
      detail: { fontWeight: '400', fontSize: '0.8125rem' },
      colorScheme: {
        dark: {
          // Success borrows the brand green; it is the one message the accent
          // is actually about.
          success: { background: 'rgba(18, 32, 22, 0.96)', borderColor: accent(0.42), color: '#d5f5e0', detailColor: '#9fcdaf' },
          info: { background: 'rgba(22, 27, 24, 0.96)', borderColor: 'rgba(255, 255, 255, 0.14)', color: '{surface.50}', detailColor: '{surface.300}' },
          error: { background: 'rgba(36, 22, 22, 0.96)', borderColor: 'rgba(224, 122, 110, 0.4)', color: '#f6d5d1', detailColor: '#d3a9a3' },
        },
      },
    },
    slider: {
      handle: { width: '0.85rem', height: '0.85rem' },
      track: { size: '4px' },
    },
    tooltip: {
      root: { fontSize: '0.75rem', padding: '0.4rem 0.6rem' },
    },
    dialog: {
      root: { borderRadius: '14px' },
      header: { padding: '1.25rem 1.25rem 0.5rem 1.25rem' },
      content: { padding: '0 1.25rem 0.5rem 1.25rem' },
      footer: { padding: '1rem 1.25rem 1.25rem 1.25rem' },
      title: { fontSize: '1.05rem', fontWeight: '700' },
    },
    popover: {
      root: { borderRadius: '12px' },
      content: { padding: '0.5rem' },
    },
    chip: {
      root: { borderRadius: '999px', paddingX: '0.7rem', paddingY: '0.2rem' },
      label: { fontSize: '0.75rem', fontWeight: '600' },
    },
    progressbar: {
      root: { height: '4px', borderRadius: '999px' },
    },
    inputtext: {
      root: { paddingX: '0.85rem', paddingY: '0.6rem' },
    },
  },
});
