// ============================================================================
//  AI Witcher Dump  (tested on The Witcher 3 Remastered v5.00b)
//  Writes character state to Documents\The Witcher 3\scriptslog.txt
//  for the witcher3 MCP server. Requires launch option: -debugscripts
//  Usage: open debug console and type:  aidump
//  If a block fails to compile, comment out its call in AIW_Dump().
// ============================================================================
function AIW_Log(text : string)
{
	LogChannel('AIWitcher', "AIW|" + text);
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

	AIW_DumpCharacter(witcher);
	AIW_DumpWorld(witcher);
	AIW_DumpEquipment(witcher);
	AIW_DumpSkills(witcher);
	AIW_DumpQuests();
	AIW_DumpInventory(witcher);

	AIW_Log("END|" + stamp);
	witcher.DisplayHudMessage("AI dump: OK");
}

// --- Level, XP, skill points, vitality, money ---
function AIW_DumpCharacter(witcher : W3PlayerWitcher)
{
	AIW_Log("CHAR|level|" + IntToString(witcher.GetLevel()));
	AIW_Log("CHAR|xp|" + IntToString(witcher.levelManager.GetPointsTotal(EExperiencePoint)));
	AIW_Log("CHAR|xp_next_level|" + IntToString(witcher.levelManager.GetTotalExpForNextLevel()));
	AIW_Log("CHAR|skill_points_free|" + IntToString(witcher.levelManager.GetPointsFree(ESkillPoint)));
	AIW_Log("CHAR|vitality|" + FloatToString(witcher.GetStat(BCS_Vitality)) + " / " + FloatToString(witcher.GetStatMax(BCS_Vitality)));
	AIW_Log("CHAR|toxicity|" + FloatToString(witcher.GetStat(BCS_Toxicity)) + " / " + FloatToString(witcher.GetStatMax(BCS_Toxicity)));
	AIW_Log("CHAR|crowns|" + IntToString(witcher.GetMoney()));
}

// --- Area, position, game time ---
function AIW_DumpWorld(witcher : W3PlayerWitcher)
{
	var t : GameTime;

	t = theGame.GetGameTime();
	AIW_Log("WORLD|area|" + NameToString(theGame.GetCommonMapManager().GetCurrentArea()));
	AIW_Log("WORLD|position|" + VecToString(witcher.GetWorldPosition()));
	AIW_Log("WORLD|game_time|day " + IntToString(GameTimeDays(t)) + ", "
		+ IntToString(GameTimeHours(t)) + ":" + IntToString(GameTimeMinutes(t)));
}

// --- Equipped gear ---
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
				+ NameToString(witcher.inv.GetItemName(item)));
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

// --- Tracked and active quests ---
function AIW_DumpQuests()
{
	var journal : CWitcherJournalManager;
	var entries : array<CJournalBase>;
	var jquest   : CJournalQuest;
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
		if (jquest && journal.GetEntryStatus(jquest) == JS_Active)
		{
			AIW_Log("QUEST|" + IntToString((int)jquest.GetType()) + "|"
				+ GetLocStringById(jquest.GetTitleStringId()));
		}
	}
}

// --- Inventory ---
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
