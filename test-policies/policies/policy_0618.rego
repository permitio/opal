package risk.authentication.user.verify.helpers.policy_0618

# Auto-generated policy 618 (Rego v1 syntax)
# Package: risk.authentication.user.verify.helpers

# Metadata
metadata := {
    "policy_id": "0618",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0618_allowed = false
policy_0618_allowed if {
    input.user.active
    input.resource.public
}
policy_0618_allowed if {
    data.policies.risk.enabled
}
