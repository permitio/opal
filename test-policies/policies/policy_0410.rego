package governance.authorization.policy.verify.policy_0410

# Auto-generated policy 410 (Rego v1 syntax)
# Package: governance.authorization.policy.verify

# Metadata
metadata := {
    "policy_id": "0410",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0410_allowed if {
    data.policies.governance.enabled
}
policy_0410_allowed if {
    input.user.active
    input.resource.public
}
