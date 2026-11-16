/* FLO Assistant's robot, the same drawing as the web launcher (frontend/src/components/assistant/Robot.tsx). */
import Svg, { Circle, G, Line, Path, Rect } from "react-native-svg";

export function Robot({ size = 30, color }: { size?: number; color: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 32 32" fill="none" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <Line x1={16} y1={4.6} x2={16} y2={8} stroke={color} strokeWidth={1.6} strokeLinecap="round" />
      <Circle cx={16} cy={3.4} r={1.7} fill={color} />
      <Rect x={6.5} y={8} width={19} height={14.5} rx={5} stroke={color} strokeWidth={1.8} />
      <Circle cx={12.4} cy={14.6} r={1.9} fill={color} />
      <Circle cx={19.6} cy={14.6} r={1.9} fill={color} />
      <Path d="M13 18.6c1.8 1.3 4.2 1.3 6 0" stroke={color} strokeWidth={1.6} strokeLinecap="round" />
      <Path d="M8.6 22.5v3.2M23.4 22.5v3.2" stroke={color} strokeWidth={1.6} strokeLinecap="round" />
      <Path d="M6.5 18.2 3.6 21" stroke={color} strokeWidth={1.6} strokeLinecap="round" />
      <G>
        <Path d="M25.5 17.8 28.6 13" stroke={color} strokeWidth={1.6} strokeLinecap="round" />
        <Circle cx={29.1} cy={12.1} r={1.6} fill={color} />
      </G>
    </Svg>
  );
}
