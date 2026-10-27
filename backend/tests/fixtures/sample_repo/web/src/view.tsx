import { formatName } from "@lib/index";

type Props = { name: string };

export default function View({ name }: Props) {
  return <div className="view">{formatName(name)}</div>;
}
