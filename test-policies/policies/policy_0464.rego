package risk.enforcement.resource.validate.data.policy_0464

# Auto-generated policy 464 (Rego v1 syntax)
# Package: risk.enforcement.resource.validate.data

# Metadata
metadata := {
    "policy_id": "0464",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0464_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0464_allowed if {
    input.user.role == "admin"
}
policy_0464_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
