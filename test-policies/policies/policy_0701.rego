package governance.validation.context.check.policy_0701

# Auto-generated policy 701 (Rego v1 syntax)
# Package: governance.validation.context.check

# Metadata
metadata := {
    "policy_id": "0701",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0701_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0701_allowed = false
policy_0701_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0701_allowed if {
    data.policies.governance.enabled
}
