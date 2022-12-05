# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare, float_is_zero, float_repr, float_round


class StockMove(models.Model):
    _inherit = "stock.move"

    product_code = fields.Char(string="Product ID", related="product_id.default_code")

    location_id = fields.Many2one(
        "stock.location",
        "Source Warehouse",
        auto_join=True,
        index=True,
        required=False,
        check_company=True,
        states={
            "new": [("required", False)],
            "draft": [("required", False)],
            "confirmed": [("readonly", False)],
        },
        help="Sets a location if you produce at a fixed location. This can be a partner location if you subcontract "
        "the manufacturing operations.",
    )

    def _domain_dest_location_id(self):
        domain = "[]"
        if (
            self.location_id
            and (self.picking_type_id.code == "internal")
            and (
                not self.env.user.has_group(
                    "oaf_stock_transfer.logistics_stock_transfer_team_group"
                )
            )
        ):
            return [("id", "in", self.location_id.allowed_location_id.ids)]
        return domain

    location_dest_id = fields.Many2one(
        "stock.location",
        "To",
        auto_join=True,
        index=True,
        required=True,
        check_company=True,
        help="Location where the system will stock the finished products.",
        domain=_domain_dest_location_id,
    )

    @api.onchange("location_id", "picking_type_id")
    def change_location_id(self):
        if (
            self.location_id
            and (self.picking_type_id.code == "internal")
            and (
                not self.env.user.has_group(
                    "oaf_stock_transfer.logistics_stock_transfer_team_group"
                )
            )
        ):
            return {
                "domain": {
                    "location_dest_id": [
                        ("id", "in", self.location_id.allowed_location_id.ids)
                    ]
                    if self.location_id.allowed_location_id
                    else False,
                }
            }

    allowed_location_id = fields.Many2many(
        "stock.location",
        string="Allowed Locations",
        related="location_id.allowed_location_id",
    )

    product_uom_qty = fields.Float(
        "Order Qty",
        digits="Product Unit of Measure",
        default=0.0,
        required=True,
        states={"done": [("readonly", True)]},
        help="This is the quantity of products from an inventory "
        "point of view. For moves in the state 'done', this is the "
        "quantity of products that were actually moved. For other "
        "moves, this is the quantity of product that is planned to "
        "be moved. Lowering this quantity does not generate a "
        "backorder. Changing this quantity on assigned moves affects "
        "the product reservation, and should be done with care.",
    )

    state = fields.Selection(
        [
            ("draft", "Manager Approval"),
            ("cancel", "Cancelled"),
            ("waiting", "Waiting Another Move"),
            ("confirmed", "Manager Approved"),
            ("partially_available", "Partially Available"),
            ("assigned", "Manager Approved"),
            ("done", "Done"),
        ],
        string="Status",
        copy=False,
        default="draft",
        index=True,
        readonly=True,
        help="* New: When the stock move is created and not yet confirmed.\n"
        "* Waiting Another Move: This state can be seen when a move is waiting for another one, for example in a chained flow.\n"
        "* Waiting Availability: This state is reached when the procurement resolution is not straight forward. It may need the scheduler to run, a component to be manufactured...\n"
        "* Available: When products are reserved, it is set to 'Available'.\n"
        "* Done: When the shipment is processed, the state is 'Done'.",
    )

    date = fields.Datetime(
        "Expected Delivery Date",
        default=fields.Datetime.now,
        index=True,
        required=True,
        help="Scheduled date until move is done, then date of actual move processing",
    )

    create_date = fields.Datetime("Order Date", index=True, readonly=True)

    @api.depends("state", "picking_id")
    def _compute_is_initial_demand_editable(self):
        for move in self:
            if not move.picking_id.immediate_transfer and move.state in [
                "draft",
                "confirmed",
            ]:
                move.is_initial_demand_editable = True
            elif (
                not move.picking_id.is_locked
                and move.state != "done"
                and move.picking_id
            ):
                move.is_initial_demand_editable = True
            else:
                move.is_initial_demand_editable = False

    def action_assign(self):
        """Check availability of picking moves.
        This has the effect of changing the state and reserve quants on available moves, and may
        also impact the state of the picking as it is computed based on move's states.
        @return: True
        """
        # self.filtered(lambda picking: picking.state == 'draft').action_confirm()
        # moves = self.mapped('move_lines').filtered(lambda move: move.state not in ('draft', 'cancel', 'done')).sorted(
        #     key=lambda move: (-int(move.priority), not bool(move.date_deadline), move.date_deadline, move.id)
        # )
        # if not moves:
        #     raise UserError(_('Nothing to check the availability for.'))
        # If a package level is done when confirmed its location can be different than where it will be reserved.
        # So we remove the move lines created when confirmed to set quantity done to the new reserved ones.
        if self.package_level_id.is_done and self.package_level_id.state == "confirmed":
            self.package_level_id.write({"is_done": False})
        self._action_assign()
        self.package_level_id.write({"is_done": True})
        return True

    def action_confirm(self):
        self._check_company()
        if (
            self.package_level_id.state == "draft"
            and not self.package_level_id.move_ids
        ):
            self.package_level_id._generate_moves()
        # call `_action_confirm` on every draft move
        if self.state == "draft":
            self._action_confirm()

        # run scheduler for moves forecasted to not have enough in stock
        if self.state not in ("draft", "cancel", "done"):
            self._trigger_scheduler()
        return True

    def action_cancel(self):
        self._action_cancel()
        return True

    def mass_duka_approval(self):
        active_ids = (
            self.env[self._name].sudo().browse(self.env.context.get("active_ids"))
        )
        if not active_ids:
            active_ids = self
        active_ids.action_assign()
