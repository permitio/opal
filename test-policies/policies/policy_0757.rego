package audit.authentication.user.deny.data.policy_0757

# Auto-generated policy 757 (Rego v1 syntax)
# Package: audit.authentication.user.deny.data

# Metadata
metadata := {
    "policy_id": "0757",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0757_allowed = false
policy_0757_allowed if {
    data.policies.audit.enabled
}
policy_0757_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0757_allowed if {
    input.user.active
    input.resource.public
}
