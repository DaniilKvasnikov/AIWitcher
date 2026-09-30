// ============================================================================
//  AI Witcher Dump v1.2  (tested on The Witcher 3 Remastered v5.00b)
//  Writes game state to Documents\The Witcher 3\scriptslog.txt
//  for the witcher3 MCP server. Requires launch option: -debugscripts
//  Usage: open debug console and type:  aidump
//  If a block fails to compile, comment out its call in AIW_Dump().
// ============================================================================
function AIW_Log(text : string)
{
	LogChannel('AIWitcher', "AIW|" + text);
}

function AIW_B(b : bool) : string
{
	if (b)
	{
		return "1";
	}
	return "0";
}

exec function aidump()
{
	AIW_Dump();
}

function AIW_Dump()
{
	var witcher : W3PlayerWitcher;
	var stamp   : string;

	witcher = GetWitcherPlayer();
	if (!witcher)
	{
		AIW_Log("ERROR|player not found - load a save first");
		return;
	}

	stamp = FloatToString(theGame.GetEngineTimeAsSeconds());
	AIW_Log("BEGIN|" + stamp);
	AIW_Log("META|version|1.2");

	AIW_DumpCharacter(witcher);
	AIW_DumpStats(witcher);
	AIW_DumpWorld(witcher);
	AIW_DumpEquipment(witcher);
	AIW_DumpSkills(witcher);
	AIW_DumpQuests();
	AIW_DumpObjectives();
	AIW_DumpBuffs(witcher);
	AIW_DumpRecipes(witcher);
	AIW_DumpGwent();
	AIW_DumpMapPins(witcher);
	AIW_DumpInventory(witcher);

	AIW_Log("END|" + stamp);
	witcher.DisplayHudMessage("AI dump: OK");
}

// --- Level, XP, skill points, vitality, money, difficulty ---
function AIW_DumpCharacter(witcher : W3PlayerWitcher)
{
	AIW_Log("CHAR|level|" + IntToString(witcher.GetLevel()));
	AIW_Log("CHAR|xp|" + IntToString(witcher.levelManager.GetPointsTotal(EExperiencePoint)));
	AIW_Log("CHAR|xp_next_level|" + IntToString(witcher.levelManager.GetTotalExpForNextLevel()));
	AIW_Log("CHAR|skill_points_free|" + IntToString(witcher.levelManager.GetPointsFree(ESkillPoint)));
	AIW_Log("CHAR|skill_points_used|" + IntToString(witcher.levelManager.GetPointsUsed(ESkillPoint)));
	AIW_Log("CHAR|skill_points_total|" + IntToString(witcher.levelManager.GetPointsTotal(ESkillPoint)));
	AIW_Log("CHAR|vitality|" + FloatToString(witcher.GetStat(BCS_Vitality)) + " / " + FloatToString(witcher.GetStatMax(BCS_Vitality)));
	AIW_Log("CHAR|toxicity|" + FloatToString(witcher.GetStat(BCS_Toxicity)) + " / " + FloatToString(witcher.GetStatMax(BCS_Toxicity)));
	AIW_Log("CHAR|crowns|" + IntToString(witcher.GetMoney()));
	AIW_Log("CHAR|difficulty|" + IntToString((int)theGame.GetDifficultyMode()));
}

// --- Combat stats (raw attribute values, formatted by the server) ---
function AIW_DumpStats(witcher : W3PlayerWitcher)
{
	var v : SAbilityAttributeValue;

	v = witcher.GetPowerStatValue(CPS_AttackPower);
	AIW_Log("STAT|attack_power|" + FloatToString(v.valueBase) + "|" + FloatToString(v.valueMultiplicative) + "|" + FloatToString(v.valueAdditive));
	v = witcher.GetPowerStatValue(CPS_SpellPower);
	AIW_Log("STAT|sign_power|" + FloatToString(v.valueBase) + "|" + FloatToString(v.valueMultiplicative) + "|" + FloatToString(v.valueAdditive));
	v = witcher.GetTotalArmor();
	AIW_Log("STAT|armor|" + FloatToString(v.valueBase) + "|" + FloatToString(v.valueMultiplicative) + "|" + FloatToString(v.valueAdditive));
}

// --- Area, position, game time ---
function AIW_DumpWorld(witcher : W3PlayerWitcher)
{
	var t : GameTime;

	t = theGame.GetGameTime();
	AIW_Log("WORLD|area|" + NameToString(theGame.GetCommonMapManager().GetCurrentArea()));
	AIW_Log("WORLD|world_path|" + theGame.GetWorld().GetDepotPath());
	AIW_Log("WORLD|position|" + VecToString(witcher.GetWorldPosition()));
	AIW_Log("WORLD|game_time|day " + IntToString(GameTimeDays(t)) + ", "
		+ IntToString(GameTimeHours(t)) + ":" + IntToString(GameTimeMinutes(t)));
}

// --- Equipped gear: slot|name|id|level|durability|max durability ---
function AIW_DumpEquipment(witcher : W3PlayerWitcher)
{
	var slots : array<EEquipmentSlots>;
	var item  : SItemUniqueId;
	var i     : int;

	slots.PushBack(EES_SteelSword);
	slots.PushBack(EES_SilverSword);
	slots.PushBack(EES_Armor);
	slots.PushBack(EES_Gloves);
	slots.PushBack(EES_Pants);
	slots.PushBack(EES_Boots);
	slots.PushBack(EES_RangedWeapon);

	for (i = 0; i < slots.Size(); i += 1)
	{
		if (witcher.GetItemEquippedOnSlot(slots[i], item))
		{
			AIW_Log("EQUIP|" + IntToString((int)slots[i]) + "|"
				+ GetLocStringByKeyExt(witcher.inv.GetItemLocalizedNameByUniqueID(item)) + "|"
				+ NameToString(witcher.inv.GetItemName(item)) + "|"
				+ IntToString(witcher.inv.GetItemLevel(item)) + "|"
				+ FloatToString(witcher.inv.GetItemDurability(item)) + "|"
				+ FloatToString(witcher.inv.GetItemMaxDurability(item)));
		}
	}
}

// --- Learned skills ---
function AIW_DumpSkills(witcher : W3PlayerWitcher)
{
	var i     : int;
	var skill : ESkill;
	var lvl   : int;

	for (i = 1; i < EnumGetMax('ESkill'); i += 1)
	{
		skill = (ESkill)i;
		lvl = witcher.GetSkillLevel(skill);
		if (lvl > 0)
		{
			AIW_Log("SKILL|" + NameToString(SkillEnumToName(skill)) + "|" + IntToString(lvl));
		}
	}
}

// --- Tracked, active, completed and failed quests ---
function AIW_DumpQuests()
{
	var journal : CWitcherJournalManager;
	var entries : array<CJournalBase>;
	var jquest  : CJournalQuest;
	var status  : EJournalStatus;
	var i       : int;

	journal = theGame.GetJournalManager();

	jquest = journal.GetTrackedQuest();
	if (jquest)
	{
		AIW_Log("TRACKED|" + GetLocStringById(jquest.GetTitleStringId()));
	}

	journal.GetActivatedOfType('CJournalQuest', entries);
	for (i = 0; i < entries.Size(); i += 1)
	{
		jquest = (CJournalQuest)entries[i];
		if (!jquest)
		{
			continue;
		}
		status = journal.GetEntryStatus(jquest);
		if (status == JS_Active)
		{
			AIW_Log("QUEST|" + IntToString((int)jquest.GetType()) + "|" + GetLocStringById(jquest.GetTitleStringId()));
		}
		else if (status == JS_Success)
		{
			AIW_Log("DONE|" + IntToString((int)jquest.GetType()) + "|" + GetLocStringById(jquest.GetTitleStringId()));
		}
		else if (status == JS_Failed)
		{
			AIW_Log("FAILED|" + IntToString((int)jquest.GetType()) + "|" + GetLocStringById(jquest.GetTitleStringId()));
		}
	}
}

// --- Current objectives of the tracked quest: status|objective|quest ---
function AIW_DumpObjectives()
{
	var journal : CWitcherJournalManager;
	var objs    : array<SJournalQuestObjectiveData>;
	var obj     : CJournalQuestObjective;
	var hl      : CJournalQuestObjective;
	var qtitle  : string;
	var i       : int;

	journal = theGame.GetJournalManager();
	journal.GetTrackedQuestObjectivesData(objs);
	for (i = 0; i < objs.Size(); i += 1)
	{
		obj = objs[i].objectiveEntry;
		if (!obj)
		{
			continue;
		}
		qtitle = "";
		if (obj.GetParentQuest())
		{
			qtitle = GetLocStringById(obj.GetParentQuest().GetTitleStringId());
		}
		AIW_Log("OBJ|" + IntToString((int)objs[i].status) + "|" + GetLocStringById(obj.GetTitleStringId()) + "|" + qtitle);
	}

	hl = journal.GetHighlightedObjective();
	if (hl)
	{
		AIW_Log("OBJHL|" + GetLocStringById(hl.GetTitleStringId()));
	}
}

// --- Active effects (potions, food, shrine buffs): type|seconds left ---
function AIW_DumpBuffs(witcher : W3PlayerWitcher)
{
	var buffs : array<CBaseGameplayEffect>;
	var i     : int;

	buffs = witcher.GetBuffs();
	for (i = 0; i < buffs.Size(); i += 1)
	{
		if (buffs[i])
		{
			AIW_Log("BUFF|" + NameToString(EffectTypeToName(buffs[i].GetEffectType())) + "|" + FloatToString(buffs[i].GetTimeLeft()));
		}
	}
}

// --- Known alchemy recipes and crafting diagrams (internal names) ---
function AIW_DumpRecipes(witcher : W3PlayerWitcher)
{
	var names : array<name>;
	var i     : int;

	names = witcher.GetAlchemyRecipes();
	for (i = 0; i < names.Size(); i += 1)
	{
		AIW_Log("RECIPE|" + NameToString(names[i]));
	}
	names = witcher.GetCraftingSchematicsNames();
	for (i = 0; i < names.Size(); i += 1)
	{
		AIW_Log("SCHEM|" + NameToString(names[i]));
	}
}

// --- Gwent collection size ---
function AIW_DumpGwent()
{
	var gm    : CR4GwintManager;
	var owned : array<CName>;
	var defs  : array<SCardDefinition>;

	gm = theGame.GetGwintManager();
	if (gm)
	{
		owned = gm.GetPlayerCollection();
		defs = gm.GetCardDefs();
		AIW_Log("GWENT|" + IntToString(owned.Size()) + "|" + IntToString(defs.Size()));
	}
}

// --- All map pins of the current world: type|tag|known|discovered|disabled|x|y|distance|name ---
function AIW_DumpMapPins(witcher : W3PlayerWitcher)
{
	var mm    : CCommonMapManager;
	var pins  : array<SCommonMapPinInstance>;
	var ppos  : Vector;
	var pname : string;
	var i     : int;

	mm = theGame.GetCommonMapManager();
	ppos = witcher.GetWorldPosition();
	pins = mm.GetMapPinInstances(theGame.GetWorld().GetDepotPath());
	for (i = 0; i < pins.Size(); i += 1)
	{
		pname = "";
		if (pins[i].customNameId > 0)
		{
			pname = GetLocStringById(pins[i].customNameId);
		}
		AIW_Log("PIN|" + NameToString(pins[i].type) + "|" + NameToString(pins[i].tag) + "|"
			+ AIW_B(pins[i].isKnown) + "|" + AIW_B(pins[i].isDiscovered) + "|" + AIW_B(pins[i].isDisabled) + "|"
			+ IntToString(RoundF(pins[i].position.X)) + "|" + IntToString(RoundF(pins[i].position.Y)) + "|"
			+ IntToString(RoundF(VecDistance2D(ppos, pins[i].position))) + "|" + pname);
	}
}

// --- Inventory: name|count|internal name ---
function AIW_DumpInventory(witcher : W3PlayerWitcher)
{
	var items : array<SItemUniqueId>;
	var i     : int;

	witcher.inv.GetAllItems(items);
	for (i = 0; i < items.Size(); i += 1)
	{
		AIW_Log("ITEM|" + GetLocStringByKeyExt(witcher.inv.GetItemLocalizedNameByUniqueID(items[i]))
			+ "|" + IntToString(witcher.inv.GetItemQuantity(items[i]))
			+ "|" + NameToString(witcher.inv.GetItemName(items[i])));
	}
}

// ============================================================================
//  Route marking (v1.2). Commands are generated by the MCP tool plan_route.
// ============================================================================

// Reveal map pins ("?" icons) by internal tags, comma separated:
//   aimark("tag1,tag2,tag3")
exec function aimark(tags : string)
{
	var mm     : CCommonMapManager;
	var pins   : array<SCommonMapPinInstance>;
	var wanted : array<string>;
	var t      : string;
	var i, j, n : int;

	wanted = StrSplit(tags, ",");
	mm = theGame.GetCommonMapManager();
	pins = mm.GetMapPinInstances(theGame.GetWorld().GetDepotPath());
	n = 0;
	for (i = 0; i < pins.Size(); i += 1)
	{
		t = NameToString(pins[i].tag);
		for (j = 0; j < wanted.Size(); j += 1)
		{
			if (t == wanted[j])
			{
				mm.SetEntityMapPinKnown(pins[i].tag, true);
				n += 1;
				break;
			}
		}
	}
	AIW_Log("MARK|" + IntToString(n) + "|" + tags);
	GetWitcherPlayer().DisplayHudMessage("AI route: marked " + IntToString(n) + " of " + IntToString(wanted.Size()));
}

// Toggle a user waypoint pin at world coordinates of the current map:
//   aipin(914, 758)     (run again with the same coordinates to remove it)
exec function aipin(x : float, y : float)
{
	var mm   : CCommonMapManager;
	var pos  : Vector;
	var area : name;
	var r, a, b : int;

	mm = theGame.GetCommonMapManager();
	area = mm.GetAreaFromWorldPath(theGame.GetWorld().GetDepotPath(), true);
	pos.X = x;
	pos.Y = y;
	pos.Z = 0;
	r = mm.ToggleUserMapPin(area, pos, 0, false, a, b);
	AIW_Log("PINSET|" + IntToString(r) + "|" + FloatToString(x) + "|" + FloatToString(y));
	GetWitcherPlayer().DisplayHudMessage("AI route: waypoint " + IntToString(r));
}