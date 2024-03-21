# not entirely, but partially from https://github.com/icebound777/PMR-SeedGenerator/blob/main/rando_modules/logic.py
# follows examples in OoT's implementation

from collections import namedtuple
from itertools import chain
from .items import PMItem
from .data.ItemList import taycet_items, item_table, progression_miscitems, item_groups
from .data.LocationsList import location_groups
from decimal import Decimal, ROUND_HALF_UP
from .options import *
from .data.item_exclusion import exclude_due_to_settings, exclude_from_taycet_placement
from .data.itemlocation_replenish import replenishing_itemlocations
from .modules.modify_itempool import get_trapped_itempool, get_randomized_itempool
from BaseClasses import ItemClassification as Ic

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from . import PaperMarioWorld


def generate_itempool(pm_world):
    world = pm_world.multiworld
    player = pm_world.player
    global random
    random = world.random

    (pool, placed_items) = get_pool_core(pm_world)
    pm_world.itempool = [pm_world.create_item(item) for item in pool]
    for (location_name, item) in placed_items.items():
        location = world.get_location(location_name, player)
        location.place_locked_item(pm_world.create_item(item, allow_arbitrary_name=True))


def get_pool_core(world: "PaperMarioWorld"):
    global random

    pool_misc_progression_items = []
    pool_other_items = []
    pool_progression_items = []
    pool_coins_only = []
    pool_illogical_consumables = []
    pool_badges = []
    pool = []
    placed_items = {}
    magical_seeds = 0

    # remove unused items from the pool

    for location in world.get_locations():

        if location.vanilla_item is None:
            continue

        item = location.vanilla_item
        itemdata = item_table[item]
        shuffle_item = True  # None for don't handle, False for place item, True for add to pool.

        # Always Placed Items

        # Sometimes placed items

        if location.name in location_groups["OverworldCoin"]:
            shuffle_item = world.options.overworld_coins.value
            if not shuffle_item:
                location.disabled = True

        if location.name in location_groups["BlockCoin"]:
            shuffle_item = world.options.coin_blocks.value
            if not shuffle_item:
                location.disabled = True

        if location.name in location_groups["FoliageCoin"]:
            shuffle_item = world.options.foliage_coins.value
            if not shuffle_item:
                location.disabled = True

        if location.name in location_groups["ShopItem"]:
            shuffle_item = world.options.include_shops.value
            if not shuffle_item:
                location.disabled = True

        if location.name in location_groups["HiddenPanel"]:
            shuffle_item = world.options.shuffle_hidden_panels.value
            if not shuffle_item:
                location.disabled = True

        if location.name in location_groups["FavorReward"]:
            # coins get shuffled only if other rewards are also shuffled
            if location.name in location_groups["FavorCoin"]:
                shuffle_item = (world.options.koot_coins.value and
                                (world.options.koot_favors.value != ShuffleKootFavors.option_Vanilla))
            else:
                shuffle_item = (world.options.koot_favors.value != ShuffleKootFavors.option_Vanilla)

            if not shuffle_item:
                location.disabled = True

        if location.name in location_groups["FavorItem"]:
            shuffle_item = (world.options.koot_favors.value == ShuffleKootFavors.option_Full_Shuffle)
            if not shuffle_item:
                location.disabled = True

        if location.name in location_groups["LetterReward"]:
            if location.name == "Goomba Village Goompapa Letter Reward 2":
                shuffle_item = (world.options.letter_rewards.value in [ShuffleLetters.option_Final_Letter_Chain_Reward,
                                                                 ShuffleLetters.option_Full_Shuffle])
            elif location.name in location_groups["LetterChain"]:
                shuffle_item = (world.options.letter_rewards.value == ShuffleLetters.option_Full_Shuffle)

            else:
                shuffle_item = (world.options.letter_rewards.value != ShuffleLetters.option_Vanilla)

            if not shuffle_item:
                location.disabled = True

        if location.name in location_groups["RadioTradeEvent"]:
            shuffle_item = world.options.trading_events.value
            if not shuffle_item:
                location.disabled = True

        if location.name in location_groups["DojoReward"]:
            shuffle_item = world.options.dojo.value
            if not shuffle_item:
                location.disabled = True

        if location.vanilla_item == "ForestPass":
            shuffle_item = (not world.options.open_forest.value)
            if not shuffle_item:
                location.disabled = True

        if location.name in location_groups["Partner"]:
            shuffle_item = world.options.partners.value
            if not shuffle_item:
                location.disabled = True

        if location.name in location_groups["Gear"]:
            # hammer 1 bush is special in that it is made to not be empty even if starting with hammer
            if location.name == "Jr. Troopa's Playground In Hammer Bush":
                shuffle_item = ((world.options.gear_shuffle_mode.value != GearShuffleMode.option_Vanilla) and
                                (world.options.starting_hammer.value == StartingHammer.option_Hammerless))
            else:
                shuffle_item = (world.options.gear_shuffle_mode.value != GearShuffleMode.option_Vanilla)
            if not shuffle_item:
                location.disabled = True

        # add it to the proper pool, or place the item
        if shuffle_item:
            # hammer bush gets shuffled as a Tayce T item if shuffling gear locations and not hammerless
            if (location.name == "Jr. Troopa's Playground In Hammer Bush" and
                    (world.options.gear_shuffle_mode.value == GearShuffleMode.option_Gear_Location_Shuffle) and
                    (world.options.starting_hammer.value != StartingHammer.option_Hammerless)):
                pool_progression_items.append(_get_random_taycet_item())

            # progression items are shuffled; include gear and star pieces from rip cheato
            elif (itemdata[1] == Ic.progression or itemdata[0] == "GEAR" or
                  (location.name in location_groups["ShopItem"] and
                   world.options.include_shops.value and "StarPiece" in item)):
                pool_progression_items.append(item)

            # some progression items need to be in replenishable locations, we only need one of each
            elif item in progression_miscitems and item not in pool_misc_progression_items:
                pool_misc_progression_items.append(item)

            # split other items into their own pools; these other pools get modified before being sent elsewhere
            elif itemdata[0] == "COIN":
                pool_coins_only.append(item)
            elif itemdata[0] == "ITEM":
                pool_illogical_consumables.append(item)
            elif itemdata[0] == "BADGE":
                pool_badges.append(item)
            else:
                pool_other_items.append(item)
        else:
            placed_items[location.name] = item

    # end of location for loop

    # at this point every location's item should be either left unshuffled or added to a pool
    # we want to modify these pools according to settings and make sure to have the right number of items

    target_itempool_size = (
            len(pool_progression_items)
            + len(pool_misc_progression_items)
            + len(pool_coins_only)
            + len(pool_illogical_consumables)
            + len(pool_badges)
            + len(pool_other_items)
    )

    # add power stars
    if world.options.power_star_hunt.value and world.total_power_stars.value > 0:
        stars_added = 0
        for name, data in item_table.items:
            if name.contains("PowerStar"):
                if stars_added >= world.total_power_stars:
                    break
                else:
                    stars_added += 1
                    pool_progression_items.append(name)

    # add item pouches
    if world.options.item_pouches.value:
        pool_other_items.extend(["PouchA", "PouchB", "PouchC", "PouchD", "PouchE"])

    # add unused badge dupes
    if world.options.unused_badge_dupes.value:
        for name, data in item_table.items():
            if data[5] and not data[6]:
                pool_badges.append(name)

    # add beta items
    if world.options.beta_items.value:
        for name, data in item_table.items():
            if data[4] and not data[6] and name not in pool_badges:
                pool_badges.append(name)

    # add progressive badges
    if world.options.progressive_badges.value:
        for name in item_groups["ProxyBadge"]:
            pool_badges.append(name)

    # add normal boots
    if world.options.starting_boots.value == StartingBoots.option_Jumpless:
        pool_progression_items.append("BootsProxy1")

    # add partner upgrade items, taking care not to add unplaceable ones (goompa upgrades)
    if world.options.partner_upgrades.value != PartnerUpgradeShuffle.option_Vanilla:
        for name, data in item_table.items():
            if data[0] == "PARTNERUPGRADE" and not data[6]:
                pool_badges.append(name)

    # adjust item pools based on settings
    items_to_remove_from_pools = get_items_to_exclude(world)

    while items_to_remove_from_pools:
        item = items_to_remove_from_pools.pop()
        if item in pool_progression_items:
            pool_progression_items.remove(item)
            continue
        if item in pool_misc_progression_items:
            pool_misc_progression_items.remove(item)
            continue
        if item in pool_badges:
            pool_badges.remove(item)
            continue
        if item in pool_other_items:
            pool_other_items.remove(item)
            continue

    # If we have set a badge pool limit and exceed that, remove random badges
    # until that condition is satisfied
    if len(pool_badges) > world.options.badge_pool_limit.value:
        random.shuffle(pool_badges)
        while len(pool_badges) > world.options.badge_pool_limit.value:
            pool_badges.pop()

    # If the item pool is the wrong size now, fix it by filling up or clearing out items
    cur_itempool_size = (
            len(pool_progression_items)
            + len(pool_misc_progression_items)
            + len(pool_coins_only)
            + len(pool_illogical_consumables)
            + len(pool_badges)
            + len(pool_other_items)
    )

    # add random tayce t items if we need to add items for some reason
    while target_itempool_size > cur_itempool_size:
        pool_illogical_consumables.append(_get_random_taycet_item())
        cur_itempool_size += 1

    # remove coins first, then consumables if we need to keep going
    if target_itempool_size < cur_itempool_size:
        random.shuffle(pool_illogical_consumables)
        while target_itempool_size < cur_itempool_size:
            if len(pool_coins_only) > 20:
                trashable_items = pool_coins_only
            else:
                trashable_items = pool_illogical_consumables
            trashable_items.pop()
            cur_itempool_size -= 1

    # Re-join the non-required items into one array
    pool_other_items.extend(pool_coins_only)
    pool_other_items.extend(pool_illogical_consumables)
    pool_other_items.extend(pool_badges)

    # Randomize consumables if needed
    pool_other_items = get_randomized_itempool(
        pool_other_items,
        world.options.consumable_item_pool.value,
        world.options.consumable_item_quality.value,
        world.options.beta_items.value
    )

    # add traps
    pool_other_items = get_trapped_itempool(
        pool_other_items,
        world.options.item_traps.value,
        world.options.koot_favors.value,
        world.options.dojo.value,
        world.options.keysanity.value,
        (world.options.power_star_hunt.value and world.options.total_power_stars.value > 0),
        world.options.beta_items.value,
        world.options.partner_upgrades.value
    )

    # now we have the full pool, we can pre place some items
    pool.extend(pool_progression_items)
    pool.extend(pool_other_items)
    pool.extend(pool_misc_progression_items)

    return pool, placed_items


def _get_random_taycet_item():
    """
    Randomly pick a Tayce T. item object chosen out of all allowed Tayce T.
    items.
    """
    return random.choice([x for x in taycet_items if x not in exclude_from_taycet_placement])


def get_items_to_exclude(world: "PaperMarioWorld") -> list:
    """
    Returns a list of items that should not be placed or given to Mario at the
    start.
    """
    excluded_items = []

    if world.options.dojo.value:
        for item_name in exclude_due_to_settings.get("do_randomize_dojo"):
            excluded_items.append(item_name)

    if world.options.start_with_goombario.value:
        excluded_items.append("Goombario")
    if world.options.start_with_kooper.value:
        excluded_items.append("Kooper")
    if world.options.start_with_bombette.value:
        excluded_items.append("Bombette")
    if world.options.start_with_parakarry.value:
        excluded_items.append("Parakarry")
    if world.options.start_with_bow.value:
        excluded_items.append("Bow")
    if world.options.start_with_watt.value:
        excluded_items.append("Watt")
    if world.options.start_with_sushie.value:
        excluded_items.append("Sushie")
    if world.options.start_with_lakilester.value:
        excluded_items.append("Lakilester")

    if world.options.open_blue_house.value:
        for item_name in exclude_due_to_settings.get("startwith_bluehouse_open"):
            excluded_items.append(item_name)

    if world.options.open_forest.value:
        for item_name in exclude_due_to_settings.get("startwith_forest_open"):
            excluded_items.append(item_name)

    if world.options.magical_seeds.value < 4:
        for item_name in exclude_due_to_settings.get("startwith_forest_open"):
            excluded_items.append(item_name)

    if world.options.bowser_castle_mode.value > BowserCastleMode.option_Vanilla:
        for item_name in exclude_due_to_settings.get("shorten_bowsers_castle"):
            excluded_items.append(item_name)
    if world.options.bowser_castle_mode.value == BowserCastleMode.option_Boss_Rush:
        for item_name in exclude_due_to_settings.get("boss_rush"):
            excluded_items.append(item_name)
    if world.options.always_speedy_spin.value:
        for item_name in exclude_due_to_settings.get("always_speedyspin"):
            excluded_items.append(item_name)
    if world.options.always_ispy.value:
        for item_name in exclude_due_to_settings.get("always_ispy"):
            excluded_items.append(item_name)
    if world.options.always_peekaboo.value:
        for item_name in exclude_due_to_settings.get("always_peekaboo"):
            excluded_items.append(item_name)
    if world.options.progressive_badges.value:
        for item_name in exclude_due_to_settings.get("do_progressive_badges"):
            excluded_items.append(item_name)

    if world.options.gear_shuffle_mode >= GearShuffleMode.option_Gear_Location_Shuffle:
        if world.options.starting_hammer.value == StartingHammer.option_Ultra:
            excluded_items.append("HammerProxy3")
        if world.options.starting_hammer.value >= StartingHammer.option_Super:
            excluded_items.append("HammerProxy2")
        if world.options.starting_hammer.value >= StartingHammer.option_Normal:
            excluded_items.append("HammerProxy1")
        if world.options.starting_boots.value == StartingBoots.option_Ultra:
            excluded_items.append("BootsProxy3")
        if world.options.starting_boots.value >= StartingBoots.option_Super:
            excluded_items.append("BootsProxy2")
        if world.options.starting_boots.value >= StartingBoots.option_Normal:
            excluded_items.append("BootsProxy1")
    if world.options.partner_upgrades.value:
        for item_name in exclude_due_to_settings.get("partner_upgrade_shuffle"):
            excluded_items.append(item_name)

    return excluded_items