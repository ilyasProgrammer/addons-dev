# -*- coding: utf-8 -*-

from openerp import api, fields, models
import datetime
from dateutil.relativedelta import relativedelta
from openerp import tools
from openerp.osv import fields as old_fields, osv


class ServiceType(models.Model):
    _inherit = 'fleet.service.type'

    product_id = fields.Many2one('product.product', string='Service')


class Contract(models.Model):
    _inherit = 'fleet.vehicle.log.contract'

    invoice_ids = fields.One2many('account.invoice', 'contract_id', string='Vendor bill')

    def scheduler_manage_auto_costs(self, cr, uid, context=None):
        super(Contract, self).scheduler_manage_auto_costs(cr, uid, context)
        # same things as in super method, but for vendor bills
        account_invoice_obj = self.pool.get('account.invoice')
        d = datetime.datetime.strptime(old_fields.date.context_today(self, cr, uid, context=context), tools.DEFAULT_SERVER_DATE_FORMAT).date()
        contract_ids = self.pool.get('fleet.vehicle.log.contract').search(cr, uid, [('state','!=','closed')], offset=0, limit=None, order=None,context=None, count=False)
        deltas = {'yearly': relativedelta(years=+1), 'monthly': relativedelta(months=+1), 'weekly': relativedelta(weeks=+1), 'daily': relativedelta(days=+1)}
        for contract in self.pool.get('fleet.vehicle.log.contract').browse(cr, uid, contract_ids, context=context):
            if (not contract.start_date) or (contract.cost_frequency == 'no') or (len(contract.cost_ids) < 1):
                continue
            break_it_down = False
            for line in contract.cost_ids:
                if not line.cost_subtype_id.product_id.id:
                    break_it_down = True
                    break
            if break_it_down:
                continue
            found = False
            last_invoice_date = contract.start_date
            if contract.generated_cost_ids:
                last_autogenerated_invoice_id = account_invoice_obj.search(cr, uid, ['&', ('contract_id','=',contract.id), ('auto_generated','=',True)], offset=0, limit=1, order='date desc',context=context, count=False)
                if last_autogenerated_invoice_id:
                    found = True
                    last_invoice_date = account_invoice_obj.browse(cr, uid, last_autogenerated_invoice_id[0], context=context).date
            startdate = datetime.datetime.strptime(last_invoice_date, tools.DEFAULT_SERVER_DATE_FORMAT).date()
            if found:
                startdate += deltas.get(contract.cost_frequency)
            while (startdate <= d) & (startdate <= datetime.datetime.strptime(contract.expiration_date, tools.DEFAULT_SERVER_DATE_FORMAT).date()):
                journal_ids = self.pool['account.journal'].search(cr, uid, [('code', '=', 'BILL')])
                journal_id = None  #  TODO  this is exeption
                if len(journal_ids) == 1:
                    journal_id = journal_ids[0]
                company = self.pool['ir.model.data'].get_object(cr, uid, 'base', 'main_company')
                account_id = contract.insurer_id.property_account_payable_id
                invoice_line_ids = []
                for line in contract.cost_ids:
                    invoice_line_ids.append((0, 0, {'name': line.cost_subtype_id.product_id.name,
                                                    'product_id': line.cost_subtype_id.product_id.id,
                                                    'quantity': 1,
                                                    'price_unit': line.amount,
                                                    'account_id': account_id.id}))
                invoice_vals = {
                    'name': '',
                    'type': 'in_invoice',
                    'auto_generated': True,
                    'partner_id':  contract.insurer_id.id,
                    'account_id':  account_id.id,
                    'journal_id':  journal_id,
                    'currency_id': company.currency_id.id,
                    'invoice_line_ids': invoice_line_ids,
                    'date_invoice': startdate,
                    'date': startdate,
                    'contract_id': contract.id,
                    'comment': contract.name,
                }
                startdate += deltas.get(contract.cost_frequency)
                new_bill = self.pool.get('account.invoice').create(cr, uid, invoice_vals, context=context)
                print '# new_bill:', new_bill
                print '# contract:', contract
        return True

    def on_change_indic_cost(self, cr, uid, ids, cost_ids, context=None):
        res = super(Contract, self).on_change_indic_cost(cr, uid, ids, cost_ids, context)
        cost_generated = 0
        for val in res['value']:
            if 'sum_cost' == val:
                res['value'].update({'cost_generated': res['value'][val], })
                break
        return res


class Invoice(models.Model):
    _inherit = 'account.invoice'

    contract_id = fields.Many2one('fleet.service.type')
    auto_generated = fields.Boolean(default=False)
