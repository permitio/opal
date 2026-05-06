package compliance.authentication.action.deny.policy_0577

# Auto-generated policy 577 (Rego v1 syntax)
# Package: compliance.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0577",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0577_allowed if {
    data.policies.compliance.enabled
}
default policy_0577_allowed = false
policy_0577_allowed if {
    input.user.active
    input.resource.public
}
policy_0577_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
