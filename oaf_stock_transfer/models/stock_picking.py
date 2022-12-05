# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from lxml import etree
import json
import time
from ast import literal_eval
from collections import defaultdict
from datetime import date
from itertools import groupby
from operator import attrgetter, itemgetter
from collections import defaultdict

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.addons.stock.models.stock_move import PROCUREMENT_PRIORITIES
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, format_datetime
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo.tools.misc import format_date


class StockPicking(models.Model):
    _inherit = "stock.picking"

    partner_id = fields.Many2one(
        "res.partner",
        "Shop Agent",
        check_company=True,
        states={"done": [("readonly", True)], "cancel": [("readonly", True)]},
    )

    location_id = fields.Many2one(
        "stock.location",
        "Source Warehouse",
        check_company=True,
        readonly=True,
        required=False,
        states={
            "new": [("readonly", False)],
            "draft": [("readonly", False), ("required", True)],
            "confirmed": [("readonly", False)],
        },
    )

    location_dest_id = fields.Many2one(
        "stock.location",
        "To",
        default=lambda self: self.env["stock.picking.type"]
        .browse(self._context.get("default_picking_type_id"))
        .default_location_dest_id,
        check_company=True,
        readonly=True,
        required=True,
        states={
            "new": [("readonly", False)],
            "draft": [("readonly", False)],
            "confirmed": [("readonly", False)],
        },
    )

    picking_type_id = fields.Many2one(
        "stock.picking.type",
        "Inventory Request",
        required=True,
        readonly=True,
        states={
            "new": [("readonly", False)],
            "draft": [("readonly", False)],
            "confirmed": [("readonly", False)],
        },
    )

    scheduled_date = fields.Datetime(
        "Expected Delivery Date",
        compute="_compute_scheduled_date",
        inverse="_set_scheduled_date",
        store=True,
        index=True,
        default=fields.Datetime.now,
        tracking=True,
        states={"done": [("readonly", True)], "cancel": [("readonly", True)]},
        help="Scheduled time for the first part of the shipment to be processed. "
        "Setting manually a value here would set it as expected date for all the stock moves.",
    )

    date = fields.Datetime(
        "Order Date",
        default=fields.Datetime.now,
        index=True,
        tracking=True,
        states={"done": [("readonly", True)], "cancel": [("readonly", True)]},
        help="Creation Date, usually the time of the order",
    )

    state = fields.Selection(
        selection_add=[
            ("draft", "Manager Approval"),
            ("waiting",),
            ("confirmed", "Manager Approved"),
            ("assigned", "Manager Approved"),
            ("done",),
            ("cancel",),
        ],
        string="Status",
        compute="_compute_state",
        copy=False,
        index=True,
        readonly=True,
        store=True,
        tracking=True,
        help=" * Draft: The transfer is not confirmed yet. Reservation doesn't apply.\n"
        " * Waiting another operation: This transfer is waiting for another operation before being ready.\n"
        ' * Waiting: The transfer is waiting for the availability of some products.\n(a) The shipping policy is "As soon as possible": no product could be reserved.\n(b) The shipping policy is "When all products are ready": not all the products could be reserved.\n'
        ' * Ready: The transfer is ready to be processed.\n(a) The shipping policy is "As soon as possible": at least one product has been reserved.\n(b) The shipping policy is "When all products are ready": all product have been reserved.\n'
        " * Done: The transfer has been processed.\n"
        " * Cancelled: The transfer has been cancelled.",
    )

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        # Hide Create button for shop agent.
        res = super(StockPicking, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        if view_type != 'search' and self.env.uid != SUPERUSER_ID:
            if not self.env.user.has_group('oaf_stock_transfer.group_stock_transfer_creator'):
                root = etree.fromstring(res['arch'])
                root.set('create', 'false')
                res['arch'] = etree.tostring(root)

        return res

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.company_id:
            self.shop_id = self.env.user.shop_id.id
        else:
            return {"domain": {"shop_id": []}}

    @api.depends(
        "move_type", "immediate_transfer", "move_lines.state", "move_lines.picking_id"
    )
    def _compute_state(self):
        """State of a picking depends on the state of its related stock.move
        - Draft: only used for "planned pickings"
        - Waiting: if the picking is not ready to be sent so if
          - (a) no quantity could be reserved at all or if
          - (b) some quantities could be reserved and the shipping policy is "deliver all at once"
        - Waiting another move: if the picking is waiting for another move
        - Ready: if the picking is ready to be sent so if:
          - (a) all quantities are reserved or if
          - (b) some quantities could be reserved and the shipping policy is "as soon as possible"
        - Done: if the picking is done.
        - Cancelled: if the picking is cancelled
        """
        picking_moves_state_map = defaultdict(dict)
        picking_move_lines = defaultdict(set)
        for move in self.env["stock.move"].search([("picking_id", "in", self.ids)]):
            picking_id = move.picking_id
            move_state = move.state
            picking_moves_state_map[picking_id.id].update(
                {
                    "any_draft": picking_moves_state_map[picking_id.id].get(
                        "any_draft", False
                    )
                    or move_state == "draft",
                    "all_cancel": picking_moves_state_map[picking_id.id].get(
                        "all_cancel", True
                    )
                    and move_state == "cancel",
                    "all_cancel_done": picking_moves_state_map[picking_id.id].get(
                        "all_cancel_done", True
                    )
                    and move_state in ("cancel", "done"),
                    "all_done_are_scrapped": picking_moves_state_map[picking_id.id].get(
                        "all_done_are_scrapped", True
                    )
                    and (move.scrapped if move_state == "done" else True),
                    "any_cancel_and_not_scrapped": picking_moves_state_map[
                        picking_id.id
                    ].get("any_cancel_and_not_scrapped", False)
                    or (move_state == "cancel" and not move.scrapped),
                }
            )
            picking_move_lines[picking_id.id].add(move.id)
        for picking in self:
            picking_id = (picking.ids and picking.ids[0]) or picking.id
            if not picking_moves_state_map[picking_id]:
                picking.state = "draft"
            elif picking_moves_state_map[picking_id][
                "any_draft"
            ] and picking.move_ids_without_package.filtered(
                lambda x: x.state not in ["draft", "cancel"]
            ):
                picking.state = "waiting"
            elif picking.move_ids_without_package.filtered(
                lambda x: x.state not in ["confirmed", "cancel", "done"]
            ) and picking.move_ids_without_package.filtered(
                lambda x: x.state in ["confirmed"]
            ):
                picking.state = "confirmed"
            elif picking_moves_state_map[picking_id]["any_draft"]:
                picking.state = "draft"
            elif picking_moves_state_map[picking_id]["all_cancel"]:
                picking.state = "cancel"
            elif picking_moves_state_map[picking_id]["all_cancel_done"]:
                if (
                    picking_moves_state_map[picking_id]["all_done_are_scrapped"]
                    and picking_moves_state_map[picking_id][
                        "any_cancel_and_not_scrapped"
                    ]
                ):
                    picking.state = "cancel"
                else:
                    picking.state = "done"
            else:
                relevant_move_state = (
                    self.env["stock.move"]
                    .browse(picking_move_lines[picking_id])
                    ._get_relevant_state_among_moves()
                )
                if picking.immediate_transfer and relevant_move_state not in (
                    "draft",
                    "cancel",
                    "done",
                ):
                    picking.state = "assigned"
                elif relevant_move_state == "partially_available":
                    picking.state = "assigned"
                else:
                    picking.state = relevant_move_state

    def action_review(self):
        self.state = "draft"

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

    @api.onchange("shop_id")
    def onchange_shop_picking_type_id(self):
        self.location_id = False
        if self.shop_id:
            picking_type_obj = self.env["stock.picking.type"].search(
                [
                    ("code", "=", "internal"),
                    ("warehouse_id.shop_id", "=", self.shop_id.id),
                ]
            )
            if picking_type_obj:
                self.location_dest_id = picking_type_obj.default_location_dest_id[0].id
                self.picking_type_id = picking_type_obj.id

    @api.onchange("picking_type_id", "partner_id")
    def onchange_picking_type(self):
        res = super(StockPicking, self).onchange_picking_type()
        self.location_id = False
        return res

    def mass_duka_approval(self):
        active_ids = (
            self.env[self._name].sudo().browse(self.env.context.get("active_ids"))
        )
        if not active_ids:
            active_ids = self
        active_ids.action_assign()


class StockLocation(models.Model):
    _inherit = "stock.location"

    allowed_location_id = fields.Many2many(
        "stock.location",
        string="Allowed Locations",
        relation="allowed_stock_location_allowed_location_base_location_rel",
        column1="allowed_location_id",
        column2="base_location_id",
    )

    @api.model
    def _search(
        self,
        args,
        offset=0,
        limit=None,
        order=None,
        count=False,
        access_rights_uid=None,
    ):
        context = dict(self._context) or {}
        if context.get("oaf_stock_transfer", False):
            args += [
                ("shop_id", "in", self.env.user.shop_ids.ids),
                ("usage", "=", "internal"),
            ]
        res = super(StockLocation, self)._search(
            args, offset, limit, order, count=count, access_rights_uid=access_rights_uid
        )
        return res
