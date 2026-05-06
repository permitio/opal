package governance.validation.action.verify.policy_0340

# Auto-generated policy 340 (Rego v1 syntax)
# Package: governance.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0340",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0340_allowed if {
    input.user.active
    input.resource.public
}
policy_0340_allowed if {
    data.policies.governance.enabled
}
