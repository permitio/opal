package audit.authentication.policy.deny.policy_0786

# Auto-generated policy 786 (Rego v1 syntax)
# Package: audit.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0786",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0786_allowed if {
    input.user.role == "admin"
}
policy_0786_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0786_allowed if {
    data.policies.audit.enabled
}
policy_0786_allowed if {
    input.user.active
    input.resource.public
}
