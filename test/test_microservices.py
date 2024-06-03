import unittest

import utils as tu
import time

class TestMicroservicesBase(unittest.TestCase):
    def setUp(self):
        # Create the test user
        self.user: dict = tu.create_user()
        self.assertIn('user_id', self.user)

        self.user_id: str = self.user['user_id']

        # Add funds to user
        self.add_funds_to_user_response: int = tu.add_credit_to_user(self.user_id, 10)
        self.assertTrue(tu.status_code_is_success(self.add_funds_to_user_response))

    def tearDown(self):
        pass

class TestOrderService(TestMicroservicesBase):
    def setUp(self):
        super().setUp()

        # create order in the order service and add item to the order
        self.order: dict = tu.create_order(self.user_id)
        self.assertIn('order_id', self.order)

        self.order_id: str = self.order['order_id']

    def tearDown(self):
        pass

    def test_orderUnknownItem(self):
        self.add_item_response = tu.add_item_to_order_with_response(self.order_id, "this-is-not-an-item-id", 1)
        self.assertTrue(tu.status_code_is_success(self.add_item_response.status_code))
        # Message is correctly sent
        self.add_item_response_json = self.add_item_response.json()
        self.assertIn('correlation_id', self.add_item_response_json)
        self.add_item_request_id = self.add_item_response_json['correlation_id']

        # Immediate status is Pending
        self.add_item_request_status = tu.find_request_status(self.add_item_request_id)
        self.status_attribute = self.add_item_request_status.json()
        self.assertIn(self.status_attribute['status'], ['Pending', 'Failed'])

        time.sleep(2)

        # Handled status is Failed
        self.add_item_request_status = tu.find_request_status(self.add_item_request_id)
        self.status_attribute = self.add_item_request_status.json()
        self.assertIn(self.status_attribute['status'], ['Failed'])

class TestOrderServiceMore(TestOrderService):
    def setUp(self):
        super().setUp()
        # add item to the stock service
        self.item1: dict = tu.create_item(5)
        self.assertIn('item_id', self.item1)
        self.item_id1: str = self.item1['item_id']
        self.add_stock_response1 = tu.add_stock(self.item_id1, 15)
        self.assertTrue(tu.status_code_is_success(self.add_stock_response1))

        # add item to the stock service
        self.item2: dict = tu.create_item(5)
        self.assertIn('item_id', self.item2)
        self.item_id2: str = self.item2['item_id']
        self.add_stock_response2 = tu.add_stock(self.item_id2, 1)
        self.assertTrue(tu.status_code_is_success(self.add_stock_response2))

    def tearDown(self):
        pass
        super().tearDown()

    def test_orderTooManyItems(self):
        # add items to order
        self.add_item_response1 = tu.add_item_to_order_with_response(self.order_id, self.item_id1, 16)
        self.assertTrue(tu.status_code_is_success(self.add_item_response1.status_code))
        # NB: Should eventually return false or rollback by the rabbitmq-consumer
        self.add_item_response_json1 = self.add_item_response1.json()
        self.assertIn('correlation_id', self.add_item_response_json1)
        self.add_item_request_id1 = self.add_item_response_json1['correlation_id']

        # Immediate status is Pending
        self.add_item_request_status1 = tu.find_request_status(self.add_item_request_id1)
        self.status_attribute1 = self.add_item_request_status1.json()
        self.assertIn(self.status_attribute1['status'], ['Pending', 'Processed'])

        time.sleep(0.5)

        # Handled status is Processed -> Design decision
        self.add_item_request_status2 = tu.find_request_status(self.add_item_request_id1)
        self.status_attribute2 = self.add_item_request_status2.json()
        self.assertIn(self.status_attribute2['status'], ['Processed'])

        # Try unsuccessful checkout
        self.checkout_response = tu.checkout_order(self.order_id)
        self.assertTrue(tu.status_code_is_success(self.checkout_response.status_code))
        self.checkout_response_json = self.checkout_response.json()
        self.assertIn('correlation_id', self.checkout_response_json)
        self.checkout_request_id = self.checkout_response_json['correlation_id']

        # Immediate status is Pending
        self.checkout_response_status = tu.find_request_status(self.checkout_request_id)
        self.status_attribute3 = self.checkout_response_status.json()
        self.assertIn(self.status_attribute3['status'], ['Pending', 'Failed'])

        time.sleep(0.5)

        # Handled status is Failed
        self.checkout_response_status2 = tu.find_request_status(self.checkout_request_id)
        self.status_attribute4 = self.checkout_response_status2.json()
        self.assertIn(self.status_attribute4['status'], ['Failed'])

    def test_sufficientStock(self):
        # add items to order
        self.add_item_response1 = tu.add_item_to_order_with_response(self.order_id, self.item_id1, 1)
        self.assertTrue(tu.status_code_is_success(self.add_item_response1.status_code))
        self.add_item_response2 = tu.add_item_to_order_with_response(self.order_id, self.item_id2, 1)
        self.assertTrue(tu.status_code_is_success(self.add_item_response2.status_code))

        # checkout order
        self.checkout_response = tu.checkout_order(self.order_id)
        self.assertTrue(tu.status_code_is_success(self.checkout_response.status_code))
        self.checkout_response_json = self.checkout_response.json()
        self.assertIn('correlation_id', self.checkout_response_json)
        self.checkout_request_id = self.checkout_response_json['correlation_id']

        # Wait for RabbitMQ
        time.sleep(0.5)

        # check credit
        self.credit_after_payment: int = tu.find_user(self.user_id)['credit']
        self.assertEqual(self.credit_after_payment, 0)

        # Handled status of order is Processed
        self.checkout_response_status = tu.find_request_status(self.checkout_request_id)
        self.status_attribute = self.checkout_response_status.json()
        self.assertIn(self.status_attribute['status'], ['Processed'])

    def test_insufficientCredit(self):
        # add items to order
        self.add_item_response1 = tu.add_item_to_order(self.order_id, self.item_id1, 2)
        self.assertTrue(tu.status_code_is_success(self.add_item_response1))
        self.add_item_response2 = tu.add_item_to_order(self.order_id, self.item_id2, 1)
        self.assertTrue(tu.status_code_is_success(self.add_item_response2))

        # checkout order
        self.checkout_response = tu.checkout_order(self.order_id)
        self.assertTrue(tu.status_code_is_success(self.checkout_response.status_code))
        self.checkout_response_json = self.checkout_response.json()
        self.assertIn('correlation_id', self.checkout_response_json)
        self.checkout_request_id = self.checkout_response_json['correlation_id']

        # Wait for RabbitMQ
        time.sleep(0.5)

        # check credit
        self.credit_after_payment: int = tu.find_user(self.user_id)['credit']
        self.assertEqual(self.credit_after_payment, 10)

        # Handled status of order is Failed
        self.checkout_response_status = tu.find_request_status(self.checkout_request_id)
        self.status_attribute = self.checkout_response_status.json()
        self.assertIn(self.status_attribute['status'], ['Failed'])

class TestMicroservices(unittest.TestCase):

    def test_stock(self):
        # Test /stock/item/create/<price>
        item: dict = tu.create_item(5)
        self.assertIn('item_id', item)

        item_id: str = item['item_id']

        # Test /stock/find/<item_id>
        item: dict = tu.find_item(item_id)
        self.assertEqual(item['price'], 5)
        self.assertEqual(item['stock'], 0)

        # Test /stock/add/<item_id>/<number>
        add_stock_response = tu.add_stock(item_id, 50)
        self.assertTrue(200 <= int(add_stock_response) < 300)

        stock_after_add: int = tu.find_item(item_id)['stock']
        self.assertEqual(stock_after_add, 50)

        # Test /stock/subtract/<item_id>/<number>
        over_subtract_stock_response = tu.subtract_stock(item_id, 200)
        self.assertTrue(tu.status_code_is_failure(int(over_subtract_stock_response)))

        subtract_stock_response = tu.subtract_stock(item_id, 15)
        self.assertTrue(tu.status_code_is_success(int(subtract_stock_response)))

        stock_after_subtract: int = tu.find_item(item_id)['stock']
        self.assertEqual(stock_after_subtract, 35)

    def test_payment(self):
        # Test /payment/pay/<user_id>/<order_id>
        user: dict = tu.create_user()
        self.assertIn('user_id', user)

        user_id: str = user['user_id']

        # Test /users/credit/add/<user_id>/<amount>
        add_credit_response = tu.add_credit_to_user(user_id, 15)
        self.assertTrue(tu.status_code_is_success(add_credit_response))

        # add item to the stock service
        item: dict = tu.create_item(5)
        self.assertIn('item_id', item)

        item_id: str = item['item_id']

        add_stock_response = tu.add_stock(item_id, 50)
        self.assertTrue(tu.status_code_is_success(add_stock_response))

        # create order in the order service and add item to the order
        order: dict = tu.create_order(user_id)
        self.assertIn('order_id', order)

        order_id: str = order['order_id']

        add_item_response = tu.add_item_to_order(order_id, item_id, 1)
        self.assertTrue(tu.status_code_is_success(add_item_response))

        add_item_response = tu.add_item_to_order(order_id, item_id, 1)
        self.assertTrue(tu.status_code_is_success(add_item_response))
        add_item_response = tu.add_item_to_order(order_id, item_id, 1)
        self.assertTrue(tu.status_code_is_success(add_item_response))

        payment_response = tu.payment_pay(user_id, 10)
        self.assertTrue(tu.status_code_is_success(payment_response))

        credit_after_payment: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit_after_payment, 5)

    def test_order(self):
        # Test /payment/pay/<user_id>/<order_id>
        user: dict = tu.create_user()
        self.assertIn('user_id', user)

        user_id: str = user['user_id']
        # create order in the order service and add item to the order
        order: dict = tu.create_order(user_id)
        self.assertIn('order_id', order)

        order_id: str = order['order_id']

        # add item to the stock service
        item1: dict = tu.create_item(5)
        self.assertIn('item_id', item1)
        item_id1: str = item1['item_id']
        add_stock_response = tu.add_stock(item_id1, 15)
        self.assertTrue(tu.status_code_is_success(add_stock_response))

        # add item to the stock service
        item2: dict = tu.create_item(5)
        self.assertIn('item_id', item2)
        item_id2: str = item2['item_id']
        add_stock_response = tu.add_stock(item_id2, 1)
        self.assertTrue(tu.status_code_is_success(add_stock_response))

        add_item_response = tu.add_item_to_order(order_id, item_id1, 1)
        self.assertTrue(tu.status_code_is_success(add_item_response))
        add_item_response = tu.add_item_to_order(order_id, item_id2, 1)
        self.assertTrue(tu.status_code_is_success(add_item_response))
        subtract_stock_response = tu.subtract_stock(item_id2, 1)
        self.assertTrue(tu.status_code_is_success(subtract_stock_response))
        stock_after_subtract: int = tu.find_item(item_id1)['stock']
        self.assertEqual(stock_after_subtract, 15)
        stock_after_subtract2: int = tu.find_item(item_id2)['stock']
        self.assertEqual(stock_after_subtract2, 0)

        checkout_response = tu.checkout_order(order_id)
        checkout_response_status = checkout_response.status_code
        # self.assertTrue(tu.status_code_is_failure(checkout_response)) failure now mediated by rabbitmq-consumer
        time.sleep(0.01)
        stock_after_subtract: int = tu.find_item(item_id1)['stock']
        self.assertEqual(stock_after_subtract, 15)

        add_stock_response = tu.add_stock(item_id2, 15)
        self.assertTrue(tu.status_code_is_success(int(add_stock_response)))

        credit_after_payment: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit_after_payment, 0)

        checkout_response = tu.checkout_order(order_id).status_code
        # self.assertTrue(tu.status_code_is_failure(checkout_response)) failure now mediated by rabbitmq-consumer
        time.sleep(0.01)
        add_credit_response = tu.add_credit_to_user(user_id, 15)
        self.assertTrue(tu.status_code_is_success(int(add_credit_response)))

        credit: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit, 15)
        stock: int = tu.find_item(item_id1)['stock']
        self.assertEqual(stock, 15)

        checkout_response = tu.checkout_order(order_id)
        self.assertTrue(tu.status_code_is_success(checkout_response.status_code))
        time.sleep(0.01)

        stock_after_subtract: int = tu.find_item(item_id1)['stock']
        self.assertEqual(stock_after_subtract, 14)

        credit: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit, 5)

if __name__ == '__main__':
    unittest.main()
