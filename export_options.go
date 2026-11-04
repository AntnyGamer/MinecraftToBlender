package main

import "strings"

type exportOptions struct {
	Dimension string
	Frames, Paintings, Stands, Displays bool
	Resume bool
}

func nextDimension(current string) string {
	switch current {
	case "overworld":
		return "the_nether"
	case "the_nether":
		return "the_end"
	default:
		return "overworld"
	}
}

func dimensionLabel(dimension string) string {
	switch dimension {
	case "the_nether":
		return "Nether"
	case "the_end":
		return "End"
	default:
		return "Overworld"
	}
}

func (o exportOptions) EntityList() string {
	var names []string
	if o.Frames {
		names = append(names, "minecraft:item_frame", "minecraft:glow_item_frame")
	}
	if o.Paintings {
		names = append(names, "minecraft:painting")
	}
	if o.Stands {
		names = append(names, "minecraft:armor_stand")
	}
	if o.Displays {
		names = append(names, "minecraft:block_display", "minecraft:item_display")
	}
	if len(names) == 0 {
		return "none"
	}
	return strings.Join(names, ",")
}
