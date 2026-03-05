import next from "eslint-config-next";

const config = [
  ...next,
  {
    name: "weaver/overrides",
    files: ["**/*.{js,jsx,ts,tsx}"],
    rules: {
      "@next/next/no-img-element": "off",
      "@typescript-eslint/ban-ts-comment": "off",
      "@typescript-eslint/no-empty-object-type": "off",
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": "off",
      "prefer-const": "off",
      "react/no-unescaped-entities": "off",
      "react-hooks/immutability": "off",
      "react-hooks/purity": "off",
      "react-hooks/set-state-in-effect": "off",
    },
  },
];

export default config;
