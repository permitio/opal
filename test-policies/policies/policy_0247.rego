package audit.authentication.resource.deny.policy_0247

# Auto-generated policy 247 (Rego v1 syntax)
# Package: audit.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0247",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0247_allowed if {
    data.policies.audit.enabled
}
policy_0247_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0247_allowed if {
    input.user.role == "admin"
}
policy_0247_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
