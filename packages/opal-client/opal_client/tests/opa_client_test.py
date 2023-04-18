import functools
import random

import pytest
from fastapi import Response, status
from opal_client.policy_store.opa_client import OpaClient


@pytest.mark.asyncio
async def test_attempt_operations_with_postponed_failure_retry():
    class OrderStrictOps:
        def __init__(self, loadable=True):
            self.next_allowed_module = 0
            self.badly_ordered_bundle = list(range(random.randint(5, 25)))

            if not loadable:
                # Remove a random module from the bundle, so dependent modules won't be able to ever load
                self.badly_ordered_bundle.pop(
                    random.randint(0, len(self.badly_ordered_bundle) - 2)
                )

            random.shuffle(self.badly_ordered_bundle)

        async def _policy_op(self, module: int) -> Response:
            if self.next_allowed_module == module:
                self.next_allowed_module += 1
                return Response(status_code=status.HTTP_200_OK)
            else:
                return Response(
                    status_code=random.choice(
                        [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND]
                    ),
                    content=f"Module {module} is in bad order, can't load before {self.next_allowed_module}",
                )

        def get_badly_ordered_ops(self):
            return [
                functools.partial(self._policy_op, module)
                for module in self.badly_ordered_bundle
            ]

    order_strict_ops = OrderStrictOps()

    # Shouldn't raise
    await OpaClient._attempt_operations_with_postponed_failure_retry(
        order_strict_ops.get_badly_ordered_ops()
    )

    order_strict_ops = OrderStrictOps(loadable=False)

    # Should raise, can't complete all operations
    with pytest.raises(RuntimeError):
        await OpaClient._attempt_operations_with_postponed_failure_retry(
            order_strict_ops.get_badly_ordered_ops()
        )
