from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple
from datetime import datetime
from operator import itemgetter
import pytz
from google.cloud.datastore import Client, Entity, Transaction
import logging

datastore_client = Client("badminton-group", "groups")
logger = logging.getLogger()


def fetch_groups(limit: int = None) -> List[Entity]:
    query = datastore_client.query(kind="group")
    query.order = ["-start_time"]
    try:
        return list(query.fetch(limit=limit))
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


def fetch_group(group_id: str, transaction: Transaction = None) -> Optional[Entity]:
    key = datastore_client.key("group", int(group_id))
    try:
        group_entity = datastore_client.get(key, transaction=transaction)
        return group_entity
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


def process_create_group(data: dict) -> Optional[str]:
    new_group = Entity(datastore_client.key("group"))
    local = pytz.timezone("US/Pacific")
    start_time = local.localize(
        datetime.strptime(data["date"] + " " + data["start_time"], "%Y-%m-%d %H:%M")
    )
    end_time = local.localize(
        datetime.strptime(data["date"] + " " + data["end_time"], "%Y-%m-%d %H:%M")
    )
    retreat_deadline = local.localize(
        datetime.strptime(data["retreat_deadline"], "%Y-%m-%dT%H:%M")
    )
    new_group.update(
        {
            "description": data["description"],
            "retreat_deadline": retreat_deadline,
            "location": data["location"],
            "start_time": start_time,
            "end_time": end_time,
            "single_limit": int(data["single_limit"]),
            "double_limit": int(data["double_limit"]),
            "pin": data["pin"],
            "single_players": [],
            "double_players": [],
        }
    )
    try:
        datastore_client.put(new_group)
        return str(new_group.id)
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


def process_groups(groups: Iterable) -> Iterator[Dict]:
    clean_groups = get_clean_data(
        groups,
        {
            ("location", str),
            ("start_time", datetime),
            ("retreat_deadline", datetime),
            ("end_time", datetime),
            ("single_limit", int),
            ("double_limit", int),
            ("single_players", list),
            ("double_players", list),
            ("description", str),
        },
    )
    for group in clean_groups:
        start_time_local: datetime = group["start_time"].astimezone(
            pytz.timezone("US/Pacific")
        )
        end_time_local: datetime = group["end_time"].astimezone(
            pytz.timezone("US/Pacific")
        )
        retreat_time_local: datetime = group["retreat_deadline"].astimezone(
            pytz.timezone("US/Pacific")
        )
        single_players, single_waitlist = process_players(
            group["single_players"], group["single_limit"]
        )
        double_players, double_waitlist = process_players(
            group["double_players"], group["double_limit"]
        )
        now_local = datetime.now().astimezone(pytz.timezone("US/Pacific"))
        can_signup: bool = start_time_local > now_local
        can_retreat: bool = retreat_time_local > now_local

        yield {
            "id": group.id,
            "location": group["location"],
            "date": start_time_local.strftime("%a,%b %-d"),
            "start_time": start_time_local.strftime("%-I:%M %p"),
            "end_time": end_time_local.strftime("%-I:%M %p"),
            "single_limit": group["single_limit"],
            "double_limit": group["double_limit"],
            "description": group["description"],
            "single_players": single_players,
            "single_waitlist": single_waitlist,
            "double_players": double_players,
            "double_waitlist": double_waitlist,
            "can_signup": can_signup,
            "can_retreat": can_retreat,
        }


def process_players(players: Iterable, limit: int) -> Tuple[List, List]:
    clean_players = get_clean_data(
        players, {("name", str), ("pin", str), ("signup_time", datetime)}
    )
    sorted_players = sorted(clean_players, key=itemgetter("signup_time"))
    if len(sorted_players) <= limit:
        return sorted_players, []
    else:
        return sorted_players[:limit], sorted_players[limit:]


def get_clean_data(
    data: Iterable, required_field_and_type: Set[Tuple[str, type]]
) -> Iterator[Entity]:
    for item in data:
        if all(
            field_name in item and isinstance(item[field_name], type_name)
            for field_name, type_name in required_field_and_type
        ):
            yield item


def get_player_list_name_by_type(player_type: str) -> Optional[str]:
    if player_type == "double":
        return "double_players"
    elif player_type == "single":
        return "single_players"
    return None


def process_add(
    group_id: str, player_type: str, player_name: str, player_pin: str
) -> Optional[str]:
    with datastore_client.transaction() as transaction:
        group_entity = fetch_group(group_id, transaction=transaction)
        if not group_entity:
            return f"Can't find group with ID {group_id}"
        player_list_name = get_player_list_name_by_type(player_type)
        player_name = player_name.strip()
        if player_name.lower() in {
            x["name"].lower() for x in group_entity[player_list_name]
        }:
            return "Player with the same name already exist"
        else:
            group_entity[player_list_name].append(
                {
                    "name": player_name,
                    "pin": player_pin,
                    "signup_time": datetime.utcnow(),
                }
            )
            try:
                datastore_client.put(group_entity)
            except Exception as e:
                logger.error(e, exc_info=True)
            return None


def process_remove(
    group_id: str, player_type: str, player_name: str, player_pin: str
) -> Optional[str]:
    player_name = player_name.strip()
    with datastore_client.transaction() as transaction:
        group_entity = fetch_group(group_id, transaction=transaction)
        if not group_entity:
            return f"Can't find group with ID {group_id}"
        player_list_name = get_player_list_name_by_type(player_type)
        for idx in range(len(group_entity[player_list_name])):
            player = group_entity[player_list_name][idx]
            if player["name"].lower() != player_name.lower():
                continue
            if player_pin in [group_entity["pin"], player["pin"]]:
                group_entity[player_list_name].pop(idx)
                try:
                    datastore_client.put(group_entity)
                except Exception as e:
                    logger.error(e, exc_info=True)
                return None
            else:
                return "Wrong PIN"
        return "Can't find player with that name"
