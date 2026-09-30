// ============================================================================
//  AI Sell Price (for The Witcher 3 Remastered 5.00b)
//  Multiplies the money Geralt receives when selling items to merchants.
//  Implemented with @wrapMethod - no vanilla files are replaced.
//
//  To change the multiplier edit the number in AISP_SellMultiplier() below
//  (1.0 = vanilla, 2.0 = twice as much) and restart the game.
//
//  Note: price shown in the shop UI stays vanilla; the bonus is paid
//  right after the sale (you will see the extra crowns in your purse).
// ============================================================================

function AISP_SellMultiplier() : float
{
	return 2.0;
}

@wrapMethod(W3GuiShopInventoryComponent)
function ReceiveItem( itemId : SItemUniqueId, giver : W3GuiBaseInventoryComponent, optional quantity : int, optional out newItemID : SItemUniqueId ) : bool
{
	var before  : int;
	var gained  : int;
	var bonus   : int;
	var success : bool;

	before = giver._inv.GetMoney();
	success = wrappedMethod( itemId, giver, quantity, newItemID );

	if ( success )
	{
		gained = giver._inv.GetMoney() - before;
		if ( gained > 0 && AISP_SellMultiplier() > 1.0 )
		{
			bonus = RoundF( gained * ( AISP_SellMultiplier() - 1.0 ) );
			if ( bonus > 0 )
			{
				giver._inv.AddMoney( bonus );
			}
		}
	}
	return success;
}
