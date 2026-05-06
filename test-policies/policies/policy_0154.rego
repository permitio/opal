package compliance.authorization.user.deny.utils.policy_0154

# Auto-generated policy 154 (Rego v1 syntax)
# Package: compliance.authorization.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0154",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0154_allowed if {
    data.policies.compliance.enabled
}
policy_0154_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
