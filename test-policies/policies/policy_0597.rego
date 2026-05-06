package risk.enforcement.action.verify.data.policy_0597

# Auto-generated policy 597 (Rego v1 syntax)
# Package: risk.enforcement.action.verify.data

# Metadata
metadata := {
    "policy_id": "0597",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0597_allowed if {
    input.user.active
    input.resource.public
}
policy_0597_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0597_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0597_allowed if {
    input.user.role == "admin"
}
